//go:build linux

package gui

import (
	"bytes"
	"errors"
	"image"
	"image/png"
	"os"
	"os/exec"
)

func detectCapabilities() (Capabilities, error) {
	if os.Getenv("WAYLAND_DISPLAY") != "" {
		if _, err := exec.LookPath("grim"); err == nil {
			return Capabilities{Capability: "linux-wayland", MaxFPS: 3, SyntheticFallback: false}, nil
		}
	}
	if os.Getenv("DISPLAY") != "" {
		for _, bin := range []string{"scrot", "import", "gnome-screenshot"} {
			if _, err := exec.LookPath(bin); err == nil {
				return Capabilities{Capability: "linux-x11", MaxFPS: 3, SyntheticFallback: false}, nil
			}
		}
	}
	return Capabilities{Capability: "none", SyntheticFallback: true, Reason: "no display server (headless)"}, nil
}

func captureScreen() (image.Image, error) {
	var raw []byte
	var err error

	switch {
	case os.Getenv("WAYLAND_DISPLAY") != "":
		raw, err = run("grim", "-")
	case hasBin("scrot"):
		raw, err = run("scrot", "-o", "/dev/stdout")
	case hasBin("import"):
		raw, err = run("import", "-window", "root", "png:-")
	case hasBin("gnome-screenshot"):
		// gnome-screenshot needs a temp file; fall back to import if possible
		return nil, errors.New("gnome-screenshot stdout capture unsupported; install scrot or grim")
	default:
		return nil, errors.New("no screenshot binary available")
	}

	if err != nil {
		return nil, err
	}
	return png.Decode(bytes.NewReader(raw))
}

func hasBin(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}

func run(name string, args ...string) ([]byte, error) {
	cmd := exec.Command(name, args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, errors.New(stderr.String())
	}
	return stdout.Bytes(), nil
}
