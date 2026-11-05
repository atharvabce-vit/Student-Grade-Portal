from auth import can, login
from database import create_table
from export import export_to_csv
from students import (
    add_student,
    delete_student,
    import_students_from_file,
    search_student,
    show_statistics,
    update_student,
    view_all_students,
)
from users import seed_default_users


def do_login():
    print("\n--- LOGIN ---")
    username = input("Username: ").strip()
    password = input("Password: ").strip()

    role = login(username, password)
    if role is None:
        print("Invalid username or password.")
        return None

    print(f"Welcome, {username}. You are logged in as {role}.")
    return role


def show_menu():
    print("\n===== STUDENT GRADE PORTAL =====")
    print("1. Add a student")
    print("2. View all students")
    print("3. Search student")
    print("4. Update student")
    print("5. Delete student")
    print("6. Class statistics")
    print("7. Import students from a file")
    print("8. Export records to CSV")
    print("9. Exit")


def menu():
    create_table()
    seed_default_users()

    role = do_login()
    if role is None:
        return

    while True:
        show_menu()
        choice = input("Enter your choice (1-9): ").strip()

        if choice == "1":
            add_student()
        elif choice == "2":
            view_all_students()
        elif choice == "3":
            search_student()
        elif choice == "4":
            update_student()
        elif choice == "5":
            if can(role, "delete"):
                delete_student()
            else:
                print("Your role does not have permission to delete records.")
        elif choice == "6":
            show_statistics()
        elif choice == "7":
            import_students_from_file()
        elif choice == "8":
            path, count = export_to_csv()
            print(f"Exported {count} student(s) to {path}")
        elif choice == "9":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter a number between 1 and 9.")


if __name__ == "__main__":
    menu()
