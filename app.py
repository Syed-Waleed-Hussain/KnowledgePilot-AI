"""KnowledgePilot AI: a local document-based RAG assistant."""

import uuid

import streamlit as st

from llm_service import generate_answer
from pdf_processor import extract_pdf_pages, split_text_into_chunks
from rag_engine import (
    add_document_chunks,
    create_vector_store,
    get_file_hash,
    load_embedding_model,
    search_relevant_chunks,
)


st.set_page_config(
    page_title="KnowledgePilot AI",
    page_icon="📚",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def get_embedding_model():
    """Cache one model so it is not downloaded again on each rerun."""
    return load_embedding_model()


def initialize_session() -> bool:
    """Create the chat and vector store state for this browser session."""
    if "session_id" not in st.session_state:
        session_id = uuid.uuid4().hex
        try:
            vector_client, collection = create_vector_store(session_id)
        except Exception as error:
            st.error(f"Could not start the vector database: {error}")
            return False

        st.session_state.session_id = session_id
        st.session_state.documents = {}
        st.session_state.chat_history = []
        st.session_state.vector_client = vector_client
        st.session_state.collection = collection
    return True


def process_uploads(uploaded_files) -> None:
    """Extract, chunk, and index each new PDF uploaded by the student."""
    try:
        embedding_model = get_embedding_model()
    except Exception as error:
        st.error(
            "Could not load the text embedding model. Check your internet "
            f"connection and try again. Details: {error}"
        )
        return

    for uploaded_file in uploaded_files:
        pdf_bytes = uploaded_file.getvalue()
        file_hash = get_file_hash(pdf_bytes)
        if file_hash in st.session_state.documents:
            st.info(f"{uploaded_file.name} is already in this session.")
            continue

        try:
            pages = extract_pdf_pages(pdf_bytes)
            chunks = split_text_into_chunks(pages)
            add_document_chunks(
                st.session_state.collection,
                chunks,
                uploaded_file.name,
                file_hash,
                embedding_model,
            )
        except Exception as error:
            st.error(f"Could not process {uploaded_file.name}: {error}")
            continue

        st.session_state.documents[file_hash] = {
            "name": uploaded_file.name,
            "pages": len(pages),
            "chunks": len(chunks),
        }
        st.success(
            f"Processed {uploaded_file.name}: {len(pages)} text pages, "
            f"{len(chunks)} chunks."
        )


def show_sources(passages) -> None:
    """Show the retrieved evidence and its real document page references."""
    st.markdown("**Retrieved sources**")
    for index, passage in enumerate(passages, start=1):
        st.markdown(
            f"**[{index}] {passage['source']} — page {passage['page']}** "
            f"(similarity: {passage['similarity']:.2f})"
        )
        st.write(passage["text"])


def show_chat_history() -> None:
    """Render the questions, answers, and evidence from this session."""
    for entry in st.session_state.chat_history:
        with st.chat_message("user"):
            st.write(entry["question"])
        with st.chat_message("assistant"):
            if entry["answer"]:
                st.write(entry["answer"])
            elif entry["passages"]:
                st.info(
                    "Answer generation is not available. Review the retrieved "
                    "passages below or configure GROQ_API_KEY."
                )
            else:
                st.warning(entry["message"])
            if entry["passages"]:
                with st.expander("View retrieved passages"):
                    show_sources(entry["passages"])


if not initialize_session():
    st.stop()

st.title("📚 KnowledgePilot AI")
st.caption("Ask questions about your own course PDFs.")

total_chunks = st.session_state.collection.count()
document_count = len(st.session_state.documents)
first_metric, second_metric, third_metric = st.columns(3)
first_metric.metric("Documents", document_count)
second_metric.metric("Indexed passages", total_chunks)
third_metric.metric("Session", "Private to this tab")

st.sidebar.header("Your documents")
uploaded_files = st.sidebar.file_uploader(
    "Upload text-based PDF files",
    type=["pdf"],
    accept_multiple_files=True,
)

if st.sidebar.button("Process PDFs", type="primary"):
    if not uploaded_files:
        st.sidebar.warning("Choose at least one PDF first.")
    else:
        with st.spinner("Extracting text and indexing your PDFs..."):
            process_uploads(uploaded_files)

if st.session_state.documents:
    st.sidebar.subheader("Processed files")
    for document in st.session_state.documents.values():
        st.sidebar.write(
            f"📄 {document['name']} "
            f"({document['pages']} pages, {document['chunks']} passages)"
        )
else:
    st.sidebar.info("No documents have been processed in this session yet.")

st.subheader("Ask a question")
if total_chunks == 0:
    st.info("Upload and process a PDF to begin searching your course material.")
else:
    with st.form("question_form"):
        question = st.text_input("What would you like to learn?")
        submitted = st.form_submit_button("Search documents")

    if submitted:
        if not question.strip():
            st.warning("Enter a question before searching.")
        else:
            try:
                embedding_model = get_embedding_model()
                with st.spinner("Searching your documents..."):
                    passages = search_relevant_chunks(
                        st.session_state.collection,
                        question.strip(),
                        embedding_model,
                    )
            except Exception as error:
                st.error(f"Document search failed: {error}")
            else:
                if not passages:
                    st.session_state.chat_history.append(
                        {
                            "question": question.strip(),
                            "answer": None,
                            "passages": [],
                            "message": (
                                "I could not find relevant text in your "
                                "processed documents."
                            ),
                        }
                    )
                    st.warning(
                        "No relevant document content was found for that "
                        "question. Try different wording or add another PDF."
                    )
                else:
                    answer = None
                    try:
                        with st.spinner("Generating an evidence-based answer..."):
                            answer = generate_answer(question.strip(), passages)
                    except Exception as error:
                        st.warning(f"Answer generation unavailable: {error}")

                    st.session_state.chat_history.append(
                        {
                            "question": question.strip(),
                            "answer": answer,
                            "passages": passages,
                            "message": "",
                        }
                    )
                    if answer:
                        st.markdown("### Answer")
                        st.write(answer)
                    else:
                        st.info(
                            "You can still inspect the retrieved passages. "
                            "To enable generated answers, set GROQ_API_KEY "
                            "in your .env file."
                        )
                    show_sources(passages)

if st.session_state.chat_history:
    st.divider()
    st.subheader("This session's chat history")
    show_chat_history()
