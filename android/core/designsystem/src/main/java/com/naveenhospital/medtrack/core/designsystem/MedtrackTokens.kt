package com.naveenhospital.medtrack.core.designsystem

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp

/**
 * Design-system scalar tokens, mirrored from tokens.source.json.
 * One source of truth for radius, spacing, elevation and layout — screens
 * read these instead of inlining magic numbers, so the whole app stays
 * visually consistent.
 */

/** Corner radii. `Chip`/`Pill` are fully rounded. */
object MedtrackRadius {
    val Tile = 12.dp
    val Control = 14.dp
    val Card = 16.dp
    val CardLg = 18.dp
    val Sheet = 24.dp
    val Pill = 999.dp

    val TileShape = RoundedCornerShape(Tile)
    val ControlShape = RoundedCornerShape(Control)
    val CardShape = RoundedCornerShape(Card)
    val CardLgShape = RoundedCornerShape(CardLg)
    val SheetShape = RoundedCornerShape(Sheet)
    val PillShape = RoundedCornerShape(percent = 50)
}

/** 4pt spacing base. */
object MedtrackSpace {
    val S1 = 4.dp
    val S2 = 8.dp
    val S3 = 12.dp
    val S4 = 16.dp
    val S5 = 18.dp
    val S6 = 24.dp
    val Gutter = 18.dp
    val Gap = 11.dp
}

/**
 * Elevation tokens expressed as Compose `shadowElevation` dp values that
 * approximate the design-system shadow ramp (row < card < pop < fab).
 */
object MedtrackElevation {
    val Row = 1.dp
    val Card = 6.dp
    val Pop = 12.dp
    val Fab = 14.dp
}

/** Layout constants. */
object MedtrackLayout {
    val TouchMin = 44.dp
    val Rail = 4.dp
}
