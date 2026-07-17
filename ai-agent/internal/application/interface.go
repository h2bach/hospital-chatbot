package application

import (
	"agent/internal/domain"
	"errors"
)

var (
	ErrIDNotFound = errors.New("error id not found")
)

type JWTService interface {
	GenerateToken(userID string) (string, error)
	GetUserIDByToken(token string) (string, error)
	InvalidateToken(token string) error
}

type SessionStore interface {
	GetAll() []domain.Session
	GetByID(id string) (domain.Session, error)
	Create() (string, error)
	Save(session domain.Session) error
	DeleteByID(id string) error
}

type UserStore interface {
	GetAll() []domain.User
	GetByID(id string) (domain.User, error)
	Save(user domain.User) error
	DeleteByID(id string) error
}
