package store

import (
	"agent/internal/application"
	"agent/internal/domain"
	"crypto/rand"
	"fmt"
	"sync"
)

// MemorySessionStore keeps transient chatbot conversations in memory.
type MemorySessionStore struct {
	mu       sync.RWMutex
	sessions map[string]domain.Session
}

func NewMemorySessionStore() *MemorySessionStore {
	return &MemorySessionStore{sessions: make(map[string]domain.Session)}
}

func (m *MemorySessionStore) GetAll() []domain.Session {
	m.mu.RLock()
	defer m.mu.RUnlock()
	result := make([]domain.Session, 0, len(m.sessions))
	for _, session := range m.sessions {
		result = append(result, session)
	}
	return result
}

func (m *MemorySessionStore) GetByID(id string) (domain.Session, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	session, exists := m.sessions[id]
	if !exists {
		return domain.Session{}, application.ErrIDNotFound
	}
	return session, nil
}

func (m *MemorySessionStore) Create() (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	id := generateUUID()
	m.sessions[id] = domain.Session{
		ID:      id,
		Context: domain.Context{Messages: []domain.Message{}, Tools: nil},
	}
	return id, nil
}

func (m *MemorySessionStore) Save(session domain.Session) error {
	m.mu.Lock()
	defer m.mu.Unlock()
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
