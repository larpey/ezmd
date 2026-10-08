// Package shapes computes areas.
package shapes

import "math"

// Circle is a round shape.
type Circle struct {
	Radius float64
}

// Area returns the area of the circle.
func (c Circle) Area() float64 {
	return math.Pi * c.Radius * c.Radius
}
