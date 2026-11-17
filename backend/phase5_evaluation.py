"""Deterministic output checks; citation validity does not prove factual accuracy."""
import re

def evaluate_answer(question, answer, passages, required_sources=()):
    ids = [int(n) for n in re.findall(r'\[(\d+)\]', answer)]
    citations = bool(ids) and all(1 <= n <= len(passages) for n in ids)
    quiz = bool(re.search(r'\b(quiz|mcqs?|multiple.choice)\b', question, re.I))
    compare = bool(re.search(r'compare|comparison', question, re.I))
    structured = None
    if quiz:
        count = re.search(r'\b(\d+)\s*(?:mcqs?|questions?)\b', question, re.I)
        words = re.search(r'\b(one|two|three|four|five)\s*(?:mcqs?|questions?)\b', question, re.I)
        expected = int(count[1]) if count else ({'one':1,'two':2,'three':3,'four':4,'five':5}[words[1].lower()] if words else 5)
        blocks = re.split(r'^### Question \d+\s*$', answer, flags=re.M)[1:]
        structured = len(blocks) == expected
        for block in blocks:
            options = re.findall(r'^- \*\*([A-D])\.\*\*\s+(.+)$', block, re.M)
            correct = re.findall(r'^\*\*Correct Answer:\*\*\s*([A-D])\s*$', block, re.M)
            explanation = re.findall(r'^\*\*Explanation:\*\*\s*(.+)$', block, re.M)
            refs = re.findall(r'\[(\d+)\]', block)
            structured = structured and len(options)==4 and {k for k,v in options}==set('ABCD') and len(correct)==1 and bool(explanation) and bool(refs) and all(1<=int(n)<=len(passages) for n in refs)
    completion = bool(answer.strip())
    if quiz and compare:
        completion = completion and bool(re.search(r'^## .*Comparison',answer,re.M|re.I)) and bool(re.search(r'^## .*Quiz',answer,re.M|re.I))
    reasons=[]
    if not passages:reasons.append('no_evidence')
    if not ids:reasons.append('missing_citations')
    elif not citations:reasons.append('unsupported_citations')
    if structured is False:reasons.append('invalid_quiz_structure')
    if not completion:reasons.append('incomplete_output')
    available={p['source'] for p in passages if 'source' in p}
    cited={passages[n-1]['source'] for n in ids if 1<=n<=len(passages) and 'source' in passages[n-1]}
    if (set(required_sources)&available)-cited:reasons.append('missing_lecture_citations')
    return dict(evidence_available=bool(passages), citation_validity=citations,
        structured_output_validity=structured, task_completion=completion,
        passed=not reasons, failure_reasons=reasons,
        factual_accuracy_evaluated=False)
