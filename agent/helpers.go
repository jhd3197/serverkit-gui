package gui

import (
	"fmt"
	"image"
)

func sprintfRes(bounds image.Rectangle) string {
	return fmt.Sprintf("%dx%d", bounds.Dx(), bounds.Dy())
}
