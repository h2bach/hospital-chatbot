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

// MemorySessionStore keeps transient chatbot conversations in memory.
type MemorySessionStore struct {
	mu       sync.RWMutex
	sessions map[string]domain.Session
}

func NewMemorySessionStore() *MemorySessionStore {
	return &MemorySessionStore{sessions: make(map[string]domain.Session)}
}

func (m *MemorySessionStore) cleanupExpiredLocked() {
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

func (m *MemorySessionStore) GetAll() []domain.Session {
	return m.GetAllForOwner("")
}

func (m *MemorySessionStore) GetAllForOwner(ownerID string) []domain.Session {
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

func (m *MemorySessionStore) GetByID(id string) (domain.Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.cleanupExpiredLocked()

	session, exists := m.sessions[id]
	if !exists {
		return domain.Session{}, application.ErrIDNotFound
	}
	return session, nil
}

func (m *MemorySessionStore) Create() (string, error) {
	return m.CreateForOwner("")
}

func (m *MemorySessionStore) CreateForOwner(ownerID string) (string, error) {
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

func (m *MemorySessionStore) Save(session domain.Session) error {
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

func (m *MemorySessionStore) DeleteByID(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.sessions[id]; !exists {
		return application.ErrIDNotFound
	}
	delete(m.sessions, id)
	return nil
}

func generateUUID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}
