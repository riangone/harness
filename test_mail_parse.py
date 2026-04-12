import re
from core.gateway.mail import MailGateway

def test():
    gw = MailGateway()
    
    # Case 1: Empty body, command in subject
    subject1 = "/generate 写一个泛型快速排序函数"
    body1 = ""
    from_addr1 = "test1@example.com"
    print(f"Testing with subject: '{subject1}', body: '{body1}'")
    task_data1 = gw.parse_email_to_task(subject1, body1, from_addr1)
    if task_data1:
        print(f"Task Input (1): '{task_data1['input']}'")
    else:
        print("Task Data 1 is None")

    # Case 2: Body contains non-matching text, command in subject
    subject2 = "/generate 写一个泛型快速排序函数"
    body2 = "Sent from my iPhone"
    from_addr2 = "test2@example.com"
    print(f"\nTesting with subject: '{subject2}', body: '{body2}'")
    task_data2 = gw.parse_email_to_task(subject2, body2, from_addr2)
    if task_data2:
        print(f"Task Input (2): '{task_data2['input']}'")
    else:
        print("Task Data 2 is None")

    # Case 3: Command in body, empty subject
    subject3 = ""
    body3 = "/generate 写一个泛型快速排序函数"
    from_addr3 = "test3@example.com"
    print(f"\nTesting with subject: '{subject3}', body: '{body3}'")
    task_data3 = gw.parse_email_to_task(subject3, body3, from_addr3)
    if task_data3:
        print(f"Task Input (3): '{task_data3['input']}'")
    else:
        print("Task Data 3 is None")
        
    # Case 4: No command, just text in subject
    subject4 = "写一个泛型快速排序函数"
    body4 = ""
    from_addr4 = "test4@example.com"
    print(f"\nTesting with subject: '{subject4}', body: '{body4}'")
    task_data4 = gw.parse_email_to_task(subject4, body4, from_addr4)
    if task_data4:
        print(f"Task Input (4): '{task_data4['input']}'")
    else:
        print("Task Data 4 is None")

    # Case 5: No command, just text in body
    subject5 = ""
    body5 = "写一个泛型快速排序函数"
    from_addr5 = "test5@example.com"
    print(f"\nTesting with subject: '{subject5}', body: '{body5}'")
    task_data5 = gw.parse_email_to_task(subject5, body5, from_addr5)
    if task_data5:
        print(f"Task Input (5): '{task_data5['input']}'")
    else:
        print("Task Data 5 is None")

if __name__ == "__main__":
    test()
