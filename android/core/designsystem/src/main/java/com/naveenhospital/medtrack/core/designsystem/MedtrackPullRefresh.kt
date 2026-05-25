package com.naveenhospital.medtrack.core.designsystem

import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp

@Composable
fun MedtrackPullRefreshBox(
    isRefreshing: Boolean,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier,
    canRefresh: () -> Boolean = { true },
    content: @Composable BoxScope.() -> Unit,
) {
    val thresholdPx = with(LocalDensity.current) { 72.dp.toPx() }
    var dragDistance by remember { mutableStateOf(0f) }

    Box(
        modifier = modifier.pointerInput(isRefreshing) {
            detectVerticalDragGestures(
                onVerticalDrag = { change, dragAmount ->
                    when {
                        dragAmount > 0f && canRefresh() -> {
                            dragDistance = (dragDistance + dragAmount).coerceAtMost(thresholdPx * 1.5f)
                            change.consume()
                        }
                        dragDistance > 0f -> {
                            dragDistance = (dragDistance + dragAmount).coerceAtLeast(0f)
                            change.consume()
                        }
                    }
                },
                onDragEnd = {
                    if (dragDistance >= thresholdPx && !isRefreshing) {
                        onRefresh()
                    }
                    dragDistance = 0f
                },
                onDragCancel = {
                    dragDistance = 0f
                },
            )
        },
    ) {
        content()
        if (isRefreshing || dragDistance > 0f) {
            CircularProgressIndicator(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 8.dp)
                    .size(24.dp),
                strokeWidth = 2.dp,
            )
        }
    }
}
