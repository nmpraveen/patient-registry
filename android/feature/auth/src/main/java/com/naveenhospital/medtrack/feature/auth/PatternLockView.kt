package com.naveenhospital.medtrack.feature.auth

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.changedToUp
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors

@Composable
fun PatternLockView(
    selectedDots: List<Int>,
    onDotSelected: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val density = LocalDensity.current
    val patternSize = 240.dp
    val targetSize = 64.dp
    val dotRadius = 14.dp
    val hitRadius = 34.dp
    val lineWidth = 5.dp
    val patternSizePx = with(density) { patternSize.toPx() }
    val dotRadiusPx = with(density) { dotRadius.toPx() }
    val hitRadiusPx = with(density) { hitRadius.toPx() }
    val lineWidthPx = with(density) { lineWidth.toPx() }
    val centers = remember(patternSizePx) { patternCenters(patternSizePx) }
    var dragPosition by remember { mutableStateOf<Offset?>(null) }

    fun selectDotAt(position: Offset) {
        val dot = patternDotAt(position = position, centers = centers, hitRadiusPx = hitRadiusPx) ?: return
        if (dot !in selectedDots) {
            onDotSelected(dot)
        }
    }

    Box(
        modifier = modifier
            .size(patternSize)
            .pointerInput(selectedDots, centers, hitRadiusPx) {
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
                    dragPosition = down.position
                    selectDotAt(down.position)
                    while (true) {
                        val event = awaitPointerEvent(pass = PointerEventPass.Initial)
                        val change = event.changes.firstOrNull() ?: continue
                        if (change.changedToUp()) {
                            dragPosition = null
                            break
                        }
                        if (change.positionChanged()) {
                            dragPosition = change.position
                            selectDotAt(change.position)
                        }
                    }
                }
            },
    ) {
        val activeColor = MedtrackColors.Primary
        val inactiveColor = MedtrackColors.Border
        val surfaceColor = MaterialTheme.colorScheme.surface
        Canvas(modifier = Modifier.size(patternSize)) {
            val selectedCenters = selectedDots.mapNotNull { centers[it] }
            selectedCenters.zipWithNext().forEach { (start, end) ->
                drawLine(
                    color = activeColor,
                    start = start,
                    end = end,
                    strokeWidth = lineWidthPx,
                    cap = StrokeCap.Round,
                )
            }
            val lastCenter = selectedCenters.lastOrNull()
            val currentDrag = dragPosition
            if (lastCenter != null && currentDrag != null) {
                drawLine(
                    color = activeColor.copy(alpha = 0.45f),
                    start = lastCenter,
                    end = currentDrag,
                    strokeWidth = lineWidthPx,
                    cap = StrokeCap.Round,
                )
            }
            centers.forEach { (dot, center) ->
                val selected = dot in selectedDots
                drawCircle(
                    color = if (selected) activeColor else surfaceColor,
                    radius = dotRadiusPx,
                    center = center,
                )
                drawCircle(
                    color = if (selected) activeColor else inactiveColor,
                    radius = dotRadiusPx,
                    center = center,
                    style = Stroke(width = 2.dp.toPx()),
                )
                if (selected) {
                    drawCircle(
                        color = surfaceColor,
                        radius = dotRadiusPx / 3f,
                        center = center,
                    )
                }
            }
        }
        Column(
            modifier = Modifier.size(patternSize),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            (0..2).forEach { row ->
                Row(
                    modifier = Modifier.size(patternSize, targetSize),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    (0..2).forEach { column ->
                        val dot = row * 3 + column + 1
                        Box(
                            modifier = Modifier
                                .size(targetSize)
                                .semantics {
                                    role = Role.Button
                                    onClick(label = "Select pattern dot $dot") {
                                        if (dot !in selectedDots) {
                                            onDotSelected(dot)
                                        }
                                        true
                                    }
                                },
                        )
                    }
                }
            }
        }
    }
}

internal fun patternCenters(sizePx: Float): Map<Int, Offset> {
    val step = sizePx / 3f
    return (0..2).flatMap { row ->
        (0..2).map { column ->
            val dot = row * 3 + column + 1
            dot to Offset(
                x = step * column + step / 2f,
                y = step * row + step / 2f,
            )
        }
    }.toMap()
}

internal fun patternDotAt(
    position: Offset,
    centers: Map<Int, Offset>,
    hitRadiusPx: Float,
): Int? =
    centers
        .filterValues { center ->
            position.x in (center.x - hitRadiusPx)..(center.x + hitRadiusPx) &&
                position.y in (center.y - hitRadiusPx)..(center.y + hitRadiusPx)
        }
        .minByOrNull { (_, center) ->
            val delta = position - center
            delta.getDistanceSquared()
        }
        ?.key
