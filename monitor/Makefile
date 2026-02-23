BINARY := rlm-monitor

.PHONY: all build fmt vet lint test clean

all: fmt vet lint test build

build:
	go build -o $(BINARY) .

fmt:
	go fmt ./...

vet:
	go vet ./...

lint:
	golangci-lint run ./...

test:
	go test ./...

clean:
	rm -f $(BINARY)
