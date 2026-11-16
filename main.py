
project_name = "KnowledgePilot AI"

def welcome(name):
    return f"Welcome {name} to {project_name}!"

student_name = input("Enter your name: ")

message = welcome(student_name)

print(message)
