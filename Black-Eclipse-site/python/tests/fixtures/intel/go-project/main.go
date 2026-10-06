"""A small Go project fixture for CIUE integration tests."""
package main

import "fmt"

type User struct {
	ID    int
	Name  string
	Email string
}

type UserService struct {
	users []User
}

func (s *UserService) CreateUser(name string, email string) User {
	user := User{ID: len(s.users) + 1, Name: name, Email: email}
	s.users = append(s.users, user)
	return user
}

func FormatUser(u User) string {
	return fmt.Sprintf("%s <%s>", u.Name, u.Email)
}

func main() {
	service := &UserService{}
	user := service.CreateUser("Ada", "ada@example.com")
	fmt.Println(FormatUser(user))
}
