//go:build !windows && !linux

package gui

import (
	"errors"
	"image"
)

func detectCapabilities() (Capabilities, error) {
	return Capabilities{Capability: "none", SyntheticFallback: true, Reason: "unsupported OS"}, nil
}

func captureScreen() (image.Image, error) {
	return nil, errors.New("screenshot capture not implemented for this OS")
}
