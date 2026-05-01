//go:build windows

package gui

import (
	"errors"
	"image"

	"github.com/kbinani/screenshot"
)

func detectCapabilities() (Capabilities, error) {
	n := screenshot.NumActiveDisplays()
	if n == 0 {
		return Capabilities{Capability: "none", SyntheticFallback: true, Reason: "no active display"}, nil
	}
	bounds := screenshot.GetDisplayBounds(0)
	return Capabilities{
		Capability:        "windows-gdi",
		Resolution:        sprintfRes(bounds),
		MaxFPS:            5,
		SyntheticFallback: false,
	}, nil
}

func captureScreen() (image.Image, error) {
	if screenshot.NumActiveDisplays() == 0 {
		return nil, errors.New("no active display (machine likely logged out)")
	}
	bounds := screenshot.GetDisplayBounds(0)
	return screenshot.CaptureRect(bounds)
}
