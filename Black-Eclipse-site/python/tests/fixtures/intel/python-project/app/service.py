from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str
    email: str


class UserRepository:
    def __init__(self) -> None:
        self._users: list[User] = []

    def insert(self, user: User) -> User:
        self._users.append(user)
        return user


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    def create_user(self, name: str, email: str) -> User:
        user = User(id=len(self.repo._users) + 1, name=name, email=email)
        return self.repo.insert(user)
