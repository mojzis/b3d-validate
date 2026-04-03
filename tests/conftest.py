"""Shared test fixtures — real build123d shapes for validation tests."""

import pytest
from build123d import (
    Box,
    BuildPart,
    Cylinder,
    Locations,
    Mode,
    Rot,
    chamfer,
)


@pytest.fixture
def clean_box():
    """Simple 20x30x10 box — should pass all checks."""
    return Box(20, 30, 10)


@pytest.fixture
def box_with_hole():
    """Box with a horizontal through-hole — creates overhanging cylinder faces."""
    with BuildPart() as bp:
        Box(30, 30, 30)
        with Locations((Rot(0, 90, 0),)):
            Cylinder(8, 40, mode=Mode.SUBTRACT)
    return bp.part


@pytest.fixture
def thin_walled():
    """Hollow box with ~0.5mm walls — should trigger wall thickness warnings."""
    with BuildPart() as bp:
        Box(20, 20, 10)
        with Locations((0, 0, 0.5)):
            Box(19, 19, 10, mode=Mode.SUBTRACT)
    return bp.part


@pytest.fixture
def tiny_chamfer():
    """Box with 0.1mm chamfers — should trigger small feature warnings."""
    with BuildPart() as bp:
        Box(20, 20, 10)
        chamfer(bp.edges(), length=0.1)
    return bp.part


@pytest.fixture
def multi_solid():
    """Two separate boxes — should warn about multiple solids."""
    with BuildPart() as bp, Locations((0, 0, 0), (50, 0, 0)):
        Box(10, 10, 10)
    return bp.part
