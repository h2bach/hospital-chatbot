package store

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
)

var ErrNotFound = errors.New("record not found")
var ErrConflict = errors.New("record already exists")

type Record map[string]any

type JSONStore struct {
	mu          sync.RWMutex
	collections map[string][]Record
	primaryKeys map[string]string
	idempotency map[string]Record
}

func Load(directory string) (*JSONStore, error) {
	store := &JSONStore{collections: map[string][]Record{}, primaryKeys: map[string]string{}, idempotency: map[string]Record{}}
	files, err := filepath.Glob(filepath.Join(directory, "*.json"))
	if err != nil { return nil, err }
	for _, file := range files {
		if filepath.Base(file) == "validation-report.json" { continue }
		body, err := os.ReadFile(file)
		if err != nil { return nil, fmt.Errorf("read %s: %w", file, err) }
		var records []Record
		if err := json.Unmarshal(body, &records); err != nil { return nil, fmt.Errorf("decode %s: %w", file, err) }
		name := strings.TrimSuffix(filepath.Base(file), ".json")
		store.collections[name] = records
		if len(records) > 0 { store.primaryKeys[name] = detectPrimaryKey(records[0]) }
	}
	if len(store.collections) == 0 { return nil, fmt.Errorf("không tìm thấy dataset JSON trong %s", directory) }
	return store, nil
}

func detectPrimaryKey(record Record) string {
	preferred := []string{"facility_id","department_id","specialty_id","service_id","doctor_id","patient_id","user_id","appointment_id","slot_id","session_id","id"}
	for _, key := range preferred { if _, ok := record[key]; ok { return key } }
	keys := make([]string,0,len(record)); for key := range record { if strings.HasSuffix(key,"_id") { keys=append(keys,key) } }
	sort.Strings(keys); if len(keys)>0 { return keys[0] }; return "id"
}

func (s *JSONStore) CollectionNames() []string {
	s.mu.RLock(); defer s.mu.RUnlock(); names:=make([]string,0,len(s.collections)); for name:=range s.collections { names=append(names,name) }; sort.Strings(names); return names
}

func (s *JSONStore) Count(collection string) int { s.mu.RLock(); defer s.mu.RUnlock(); return len(s.collections[collection]) }

func (s *JSONStore) List(collection string, offset, limit int, filters map[string]string) ([]Record, int, error) {
	s.mu.RLock(); defer s.mu.RUnlock(); records,ok:=s.collections[collection]; if !ok { return nil,0,ErrNotFound }
	matched:=make([]Record,0)
	for _,record:=range records { good:=true; for key,value:=range filters { if fmt.Sprint(record[key])!=value { good=false; break } }; if good { matched=append(matched,clone(record)) } }
	total:=len(matched); if offset>total { offset=total }; end:=offset+limit; if end>total { end=total }; return matched[offset:end],total,nil
}

func (s *JSONStore) Get(collection,id string) (Record,error) {
	s.mu.RLock(); defer s.mu.RUnlock(); records,ok:=s.collections[collection]; if !ok { return nil,ErrNotFound }; key:=s.primaryKeys[collection]
	for _,record:=range records { if fmt.Sprint(record[key])==id { return clone(record),nil } }; return nil,ErrNotFound
}

func (s *JSONStore) Create(collection string, record Record) (Record,error) {
	s.mu.Lock(); defer s.mu.Unlock(); records,ok:=s.collections[collection]; if !ok { return nil,ErrNotFound }; key:=s.primaryKeys[collection]; id:=fmt.Sprint(record[key]); if id=="" || id=="<nil>" { return nil,fmt.Errorf("thiếu khóa chính %s",key) }
	for _,existing:=range records { if fmt.Sprint(existing[key])==id { return nil,ErrConflict } }; s.collections[collection]=append(records,clone(record)); return clone(record),nil
}

func (s *JSONStore) Update(collection,id string, patch Record) (Record,error) {
	s.mu.Lock(); defer s.mu.Unlock(); records,ok:=s.collections[collection]; if !ok { return nil,ErrNotFound }; key:=s.primaryKeys[collection]
	for i,record:=range records { if fmt.Sprint(record[key])==id { for k,v:=range patch { if k!=key { record[k]=v } }; records[i]=record; return clone(record),nil } }; return nil,ErrNotFound
}

func (s *JSONStore) Delete(collection,id string) error {
	s.mu.Lock(); defer s.mu.Unlock(); records,ok:=s.collections[collection]; if !ok { return ErrNotFound }; key:=s.primaryKeys[collection]
	for i,record:=range records { if fmt.Sprint(record[key])==id { s.collections[collection]=append(records[:i],records[i+1:]...); return nil } }; return ErrNotFound
}

func (s *JSONStore) Idempotent(key string, create func() (Record,error)) (Record,bool,error) {
	s.mu.RLock(); existing,ok:=s.idempotency[key]; s.mu.RUnlock(); if ok { return clone(existing),true,nil }
	record,err:=create(); if err!=nil { return nil,false,err }; s.mu.Lock(); s.idempotency[key]=clone(record); s.mu.Unlock(); return record,false,nil
}

func clone(record Record) Record { body,_:=json.Marshal(record); var result Record; _=json.Unmarshal(body,&result); return result }
