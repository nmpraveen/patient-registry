package com.naveenhospital.medtrack.core.designsystem

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable
fun MedtrackPage(
    title: String,
    modifier: Modifier = Modifier,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Row(content = actions)
        }
        content()
    }
}

@Composable
fun MedtrackCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = MedtrackRadius.CardShape,
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
        shadowElevation = MedtrackElevation.Row,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            content = content,
        )
    }
}

@Composable
fun MedtrackCompactCard(
    modifier: Modifier = Modifier,
    borderColor: Color = MedtrackColors.Border,
    content: @Composable ColumnScope.() -> Unit,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = Color.White,
        border = BorderStroke(1.dp, borderColor),
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
            content = content,
        )
    }
}

data class MedtrackCategoryVisual(
    val tint: Color,
    val soft: Color,
    val iconResId: Int,
)

fun medtrackCategoryVisual(
    categoryName: String?,
    label: String?,
): MedtrackCategoryVisual {
    val key = listOfNotNull(categoryName, label)
        .joinToString(" ")
        .trim()
        .lowercase()
    return when {
        key.contains("rehab") -> MedtrackCategoryVisual(
            tint = MedtrackColors.CustomRehab,
            soft = MedtrackColors.CustomRehabSoft,
            iconResId = R.drawable.ic_cat_rehab,
        )
        key.contains("anc") -> MedtrackCategoryVisual(
            tint = MedtrackColors.Anc,
            soft = MedtrackColors.AncSoft,
            iconResId = R.drawable.ic_cat_anc,
        )
        key.contains("surgery") || key.contains("surgical") -> MedtrackCategoryVisual(
            tint = MedtrackColors.Surgery,
            soft = MedtrackColors.SurgerySoft,
            iconResId = R.drawable.ic_cat_surgery,
        )
        key.contains("medicine") || key.contains("medical") -> MedtrackCategoryVisual(
            tint = MedtrackColors.Medicine,
            soft = MedtrackColors.MedicineSoft,
            iconResId = R.drawable.ic_cat_medicine,
        )
        else -> MedtrackCategoryVisual(
            tint = MedtrackColors.Primary,
            soft = MedtrackColors.PrimarySoft,
            iconResId = R.drawable.ic_cat_medicine,
        )
    }
}

@Composable
fun MedtrackCategoryTile(
    iconResId: Int,
    tint: Color,
    modifier: Modifier = Modifier,
    softColor: Color = tint.copy(alpha = 0.12f),
    size: Dp = 46.dp,
    radius: Dp = 13.dp,
    contentDescription: String? = null,
) {
    Surface(
        modifier = modifier.size(size),
        shape = RoundedCornerShape(radius),
        color = softColor,
        border = BorderStroke(1.dp, tint.copy(alpha = 0.16f)),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(
                painter = painterResource(iconResId),
                contentDescription = contentDescription,
                tint = tint,
                modifier = Modifier.size(size * 0.56f),
            )
        }
    }
}

@Composable
fun MedtrackCategoryChip(
    text: String,
    tint: Color,
    modifier: Modifier = Modifier,
    softColor: Color = tint.copy(alpha = 0.12f),
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = softColor,
        border = BorderStroke(1.dp, tint.copy(alpha = 0.2f)),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            color = tint,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
fun MedtrackRiskFlag(
    count: Int?,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
) {
    val actualModifier = if (onClick == null) modifier else modifier.clickable(onClick = onClick)
    Surface(
        modifier = actualModifier.widthIn(min = 38.dp),
        shape = RoundedCornerShape(50),
        color = MedtrackColors.DangerSoft,
        border = BorderStroke(1.dp, MedtrackColors.DangerLine),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = if (count == null) 9.dp else 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.Flag,
                contentDescription = "Red flag",
                tint = MedtrackColors.Danger,
                modifier = Modifier.size(16.dp),
            )
            count?.let {
                Text(
                    text = it.coerceAtLeast(1).toString(),
                    color = MedtrackColors.Danger,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
fun MedtrackMetricCard(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    MedtrackCard(modifier = modifier) {
        Text(text = value, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(text = label, style = MaterialTheme.typography.bodyMedium, color = MedtrackColors.Muted)
    }
}

@Composable
fun MedtrackStatCard(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = value,
                    color = color,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                )
                icon?.let {
                    Icon(
                        imageVector = it,
                        contentDescription = null,
                        tint = color,
                        modifier = Modifier.size(19.dp),
                    )
                }
            }
            Text(
                text = label,
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
fun MedtrackMiniPill(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.12f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.24f)),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            color = color,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
fun MedtrackSectionEyebrow(
    title: String,
    trailing: String? = null,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title.uppercase(),
            color = MedtrackColors.Muted,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.ExtraBold,
        )
        trailing?.let {
            Text(
                text = it,
                color = MedtrackColors.Faint,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
fun MedtrackIconBadge(
    icon: ImageVector,
    tint: Color,
    modifier: Modifier = Modifier,
    contentDescription: String? = null,
) {
    Surface(
        modifier = modifier.size(38.dp),
        shape = RoundedCornerShape(11.dp),
        color = tint.copy(alpha = 0.12f),
    ) {
        Row(horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            Icon(
                imageVector = icon,
                contentDescription = contentDescription,
                tint = tint,
                modifier = Modifier.size(20.dp),
            )
        }
    }
}

@Composable
fun MedtrackSectionTitle(
    title: String,
    trailing: String? = null,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title,
            color = MedtrackColors.Ink,
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
        )
        trailing?.let {
            Text(
                text = it,
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
fun MedtrackStatusPill(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.12f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.28f)),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            color = color,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/** Human due-state tones for [MedtrackDuePill]. */
enum class MedtrackDueTone { Today, Overdue, Upcoming, Awaiting }

/**
 * A calm, solid-tint due/state pill — "Due today", "Overdue 2 days".
 * One canonical pill so due labels read the same everywhere.
 */
@Composable
fun MedtrackDuePill(
    text: String,
    tone: MedtrackDueTone,
    modifier: Modifier = Modifier,
) {
    val color: Color
    val background: Color
    when (tone) {
        MedtrackDueTone.Today -> {
            color = MedtrackColors.Primary
            background = MedtrackColors.PrimarySoft
        }
        MedtrackDueTone.Overdue -> {
            color = MedtrackColors.Danger
            background = MedtrackColors.DangerSoft
        }
        MedtrackDueTone.Awaiting -> {
            color = MedtrackColors.Warning
            background = MedtrackColors.WarningSoft
        }
        MedtrackDueTone.Upcoming -> {
            color = MedtrackColors.Muted
            background = MedtrackColors.SurfaceAlt
        }
    }
    Surface(
        modifier = modifier,
        shape = MedtrackRadius.PillShape,
        color = background,
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            color = color,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
fun MedtrackDividerSpace() {
    Spacer(modifier = Modifier.height(4.dp))
}
