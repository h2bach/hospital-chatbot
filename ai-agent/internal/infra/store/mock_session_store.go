package store

import (
	"agent/internal/application"
	"agent/internal/domain"
	"crypto/rand"
	"fmt"
	"sync"
	"time"
)

const SessionTTL = 24 * time.Hour // 1 day auto-reset TTL

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

func (m *MockSessionStore) cleanupExpiredLocked() {
	now := time.Now()
	for id, session := range m.sessions {
		refTime := session.CreatedAt
		if !session.UpdatedAt.IsZero() {
			refTime = session.UpdatedAt
		}
		if !refTime.IsZero() && now.Sub(refTime) > SessionTTL {
			delete(m.sessions, id)
		}
	}
}

// GetAll returns all non-expired active sessions in the store.
func (m *MockSessionStore) GetAll() []domain.Session {
	return m.GetAllForOwner("")
}

// GetAllForOwner returns non-expired sessions belonging to a specific device/owner.
func (m *MockSessionStore) GetAllForOwner(ownerID string) []domain.Session {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.cleanupExpiredLocked()

	result := make([]domain.Session, 0, len(m.sessions))
	for _, session := range m.sessions {
		if ownerID == "" || session.OwnerID == "" || session.OwnerID == ownerID {
			result = append(result, session)
		}
	}
	return result
}

// GetByID retrieves a session by its ID. Returns application.ErrIDNotFound if not found or expired.
func (m *MockSessionStore) GetByID(id string) (domain.Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.cleanupExpiredLocked()

	session, exists := m.sessions[id]
	if !exists {
		return domain.Session{}, application.ErrIDNotFound
	}
	return session, nil
}

// Create generates a new session with a random UUID for default owner.
func (m *MockSessionStore) Create() (string, error) {
	return m.CreateForOwner("")
}

// CreateForOwner generates a new session for a specific device/owner.
func (m *MockSessionStore) CreateForOwner(ownerID string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.cleanupExpiredLocked()

	now := time.Now()
	id := generateUUID()
	session := domain.Session{
		ID:        id,
		Title:     "",
		OwnerID:   ownerID,
		CreatedAt: now,
		UpdatedAt: now,
		Context: domain.Context{
			Messages: []domain.Message{},
			Tools:    nil,
		},
	}
	m.sessions[id] = session
	return id, nil
}

// Save persists the session state in-memory and updates timestamp.
func (m *MockSessionStore) Save(session domain.Session) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	now := time.Now()
	if session.CreatedAt.IsZero() {
		session.CreatedAt = now
	}
	session.UpdatedAt = now
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
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}
