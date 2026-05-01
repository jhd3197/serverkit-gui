// Package gui implements the gui:capabilities and gui:screenshot agent actions.
//
// This is platform-dispatched: each OS gets its own file with build tags.
// The shared logic lives here.
package gui

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"time"

	"golang.org/x/image/draw"
)

// Params accepted by gui:screenshot.
type ScreenshotParams struct {
	Scale   float64 `json:"scale"`
	Quality int     `json:"quality"`
	Format  string  `json:"format"`
}

// Frame is the payload returned to the panel.
type Frame struct {
	ImageBase64 string `json:"image_base64"`
	Format      string `json:"format"`
	Width       int    `json:"width"`
	Height      int    `json:"height"`
	CapturedAt  string `json:"captured_at"`
}

// Capabilities is the payload returned by gui:capabilities.
type Capabilities struct {
	Capability        string `json:"capability"`
	Resolution        string `json:"resolution,omitempty"`
	MaxFPS            int    `json:"max_fps"`
	SyntheticFallback bool   `json:"synthetic_fallback"`
	Reason            string `json:"reason,omitempty"`
}

// HandleCapabilities resolves what the host can do. Wired into the agent's
// action dispatcher as "gui:capabilities".
func HandleCapabilities(_ json.RawMessage) (any, error) {
	caps, err := detectCapabilities()
	if err != nil {
		return Capabilities{
			Capability:        "none",
			SyntheticFallback: true,
			Reason:            err.Error(),
		}, nil
	}
	return caps, nil
}

// HandleScreenshot captures a single frame. Wired as "gui:screenshot".
func HandleScreenshot(raw json.RawMessage) (any, error) {
	params := ScreenshotParams{Scale: 0.75, Quality: 70, Format: "jpeg"}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &params)
	}
	if params.Scale <= 0 || params.Scale > 1 {
		params.Scale = 0.75
	}
	if params.Quality < 10 || params.Quality > 95 {
		params.Quality = 70
	}
	if params.Format != "png" && params.Format != "jpeg" {
		params.Format = "jpeg"
	}

	img, err := captureScreen()
	if err != nil {
		return nil, fmt.Errorf("capture failed: %w", err)
	}

	if params.Scale < 1.0 {
		img = downscale(img, params.Scale)
	}

	var buf bytes.Buffer
	switch params.Format {
	case "png":
		if err := png.Encode(&buf, img); err != nil {
			return nil, fmt.Errorf("png encode: %w", err)
		}
	default:
		if err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: params.Quality}); err != nil {
			return nil, fmt.Errorf("jpeg encode: %w", err)
		}
	}

	bounds := img.Bounds()
	return Frame{
		ImageBase64: base64.StdEncoding.EncodeToString(buf.Bytes()),
		Format:      params.Format,
		Width:       bounds.Dx(),
		Height:      bounds.Dy(),
		CapturedAt:  time.Now().UTC().Format(time.RFC3339),
	}, nil
}

func downscale(src image.Image, scale float64) image.Image {
	b := src.Bounds()
	w := int(float64(b.Dx()) * scale)
	h := int(float64(b.Dy()) * scale)
	dst := image.NewRGBA(image.Rect(0, 0, w, h))
	draw.CatmullRom.Scale(dst, dst.Bounds(), src, b, draw.Over, nil)
	return dst
}
