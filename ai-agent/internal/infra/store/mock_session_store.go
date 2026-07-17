package store

import (
	"agent/internal/application"
	"agent/internal/domain"
	"crypto/rand"
	"fmt"
	"sync"
)

// MockSessionStore implements application.SessionStore using in-memory map.
type MockSessionStore struct {
	mu       sync.RWMutex
	sessions map[string]domain.Session
}

// NewMockSessionStore creates a new instance of MockSessionStore.
func NewMockSessionStore() *MockSessionStore {
	return &MockSessionStore{
		sessions: make(map[string]domain.Session),
	}
}

// GetAll returns all active sessions in the store.
func (m *MockSessionStore) GetAll() []domain.Session {
	m.mu.RLock()
	defer m.mu.RUnlock()

	result := make([]domain.Session, 0, len(m.sessions))
	for _, session := range m.sessions {
		result = append(result, session)
	}
	return result
}

// GetByID retrieves a session by its ID. Returns application.ErrIDNotFound if not found.
func (m *MockSessionStore) GetByID(id string) (domain.Session, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	session, exists := m.sessions[id]
	if !exists {
		return domain.Session{}, application.ErrIDNotFound
	}
	return session, nil
}

// Create generates a new session with a random UUID, saves it, and returns the ID.
func (m *MockSessionStore) Create() (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	id := generateUUID()
	session := domain.Session{
		ID:    id,
		Title: "",
		Context: domain.Context{
			Messages: []domain.Message{},
			Tools:    nil,
		},
	}
	m.sessions[id] = session
	return id, nil
}

// Save persists the session state in-memory.
func (m *MockSessionStore) Save(session domain.Session) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.sessions[session.ID] = session
	return nil
}

// DeleteByID removes a session by ID. Returns application.ErrIDNotFound if not found.
func (m *MockSessionStore) DeleteByID(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.sessions[id]; !exists {
		return application.ErrIDNotFound
	}
	delete(m.sessions, id)
	return nil
}

// generateUUID creates a simple standard UUID v4 string using crypto/rand.
func generateUUID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	// Set the version to 4 (pseudorandom)
	b[6] = (b[6] & 0x0f) | 0x40
	// Set the variant to 10xx (RFC4122)
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}
