package com.naveenhospital.medtrack.feature.auth

import androidx.compose.ui.geometry.Offset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PatternLockViewTest {
    @Test
    fun patternCentersUseNineEvenlySpacedDots() {
        val centers = patternCenters(240f)

        assertEquals(9, centers.size)
        assertEquals(Offset(40f, 40f), centers[1])
        assertEquals(Offset(120f, 120f), centers[5])
        assertEquals(Offset(200f, 200f), centers[9])
    }

    @Test
    fun patternDotAtReturnsNearestDotInsideHitRadius() {
        val centers = patternCenters(240f)

        assertEquals(1, patternDotAt(Offset(42f, 41f), centers, hitRadiusPx = 34f))
        assertEquals(5, patternDotAt(Offset(124f, 119f), centers, hitRadiusPx = 34f))
        assertEquals(9, patternDotAt(Offset(198f, 202f), centers, hitRadiusPx = 34f))
    }

    @Test
    fun patternDotAtIgnoresPointerOutsideAllDots() {
        val centers = patternCenters(240f)

        assertNull(patternDotAt(Offset(80f, 80f), centers, hitRadiusPx = 20f))
    }
}
