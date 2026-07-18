package store

import "testing"

func TestSessionsAreStrictlyIsolatedByDeviceOwner(t *testing.T) {
	store := NewMemorySessionStore()
	first, err := store.CreateForOwner("device-a")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.CreateForOwner("device-b"); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Create(); err != nil {
		t.Fatal(err)
	}

	owned := store.GetAllForOwner("device-a")
	if len(owned) != 1 || owned[0].ID != first {
		t.Fatalf("device-a sessions = %#v, want only %s", owned, first)
	}
	if anonymous := store.GetAllForOwner(""); len(anonymous) != 1 || anonymous[0].OwnerID != "" {
		t.Fatalf("anonymous sessions leaked another device: %#v", anonymous)
	}
}
