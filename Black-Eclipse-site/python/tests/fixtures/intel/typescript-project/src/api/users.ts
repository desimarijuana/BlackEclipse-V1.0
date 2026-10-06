import { User, UserService, formatUser } from '../services/user';

const service = new UserService();

export function handleCreateUser(name: string, email: string): User {
  const user = service.createUser(name, email);
  console.log(formatUser(user));
  return user;
}

export function handleFindUser(id: number): User | undefined {
  return service.findUser(id);
}
