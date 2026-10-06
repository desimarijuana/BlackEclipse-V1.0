export interface User {
  id: number;
  name: string;
  email: string;
}

export class UserService {
  private users: User[] = [];

  createUser(name: string, email: string): User {
    const user: User = { id: this.users.length + 1, name, email };
    this.users.push(user);
    return user;
  }

  findUser(id: number): User | undefined {
    return this.users.find((u) => u.id === id);
  }
}

export function formatUser(user: User): string {
  return `${user.name} <${user.email}>`;
}
