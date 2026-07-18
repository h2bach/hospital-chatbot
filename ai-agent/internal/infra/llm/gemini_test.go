package llm

import (
	"reflect"
	"testing"
)

func TestParseAPIKeys(t *testing.T) {
	got := parseAPIKeys(" key-one, 'key-two'\nkey-one;\"key-three\" ")
	want := []string{"key-one", "key-two", "key-three"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("parseAPIKeys() = %#v, want %#v", got, want)
	}
}

func TestParseAPIKeysEmpty(t *testing.T) {
	if got := parseAPIKeys(" , ; \n"); len(got) != 0 {
		t.Fatalf("parseAPIKeys() = %#v, want no keys", got)
	}
}
