from app.service import UserService, UserRepository


def checks_create_user() -> None:
    service = UserService(UserRepository())
    user = service.create_user("Ada", "ada@example.com")
    assert user.name == "Ada"
    assert user.id == 1
