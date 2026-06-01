package com.naveenhospital.medtrack.core.designsystem

import android.os.Build
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight

private val MedtrackLightColorScheme = lightColorScheme(
    primary = MedtrackColors.Primary,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD9E6FF),
    onPrimaryContainer = MedtrackColors.PrimaryDark,
    secondary = MedtrackColors.Surgery,
    onSecondary = Color.White,
    tertiary = MedtrackColors.Medicine,
    background = MedtrackColors.Surface,
    onBackground = MedtrackColors.Ink,
    surface = MedtrackColors.Card,
    onSurface = MedtrackColors.Ink,
    surfaceVariant = Color(0xFFEAF0F8),
    onSurfaceVariant = MedtrackColors.Muted,
    outline = MedtrackColors.Border,
    error = MedtrackColors.Danger,
)

private val ManropeFontFamily by lazy {
    FontFamily(
        manropeFont(FontWeight.Normal, 400),
        manropeFont(FontWeight.Medium, 500),
        manropeFont(FontWeight.SemiBold, 600),
        manropeFont(FontWeight.Bold, 700),
        manropeFont(FontWeight.ExtraBold, 800),
    )
}

@OptIn(ExperimentalTextApi::class)
private fun manropeFont(weight: FontWeight, axisWeight: Int): Font =
    Font(
        R.font.manrope_variable,
        weight = weight,
        variationSettings = FontVariation.Settings(FontVariation.weight(axisWeight)),
    )

object MedtrackType {
    val Mono: FontFamily by lazy {
        FontFamily(
            Font(R.font.geist_mono, weight = FontWeight.Normal),
            Font(R.font.geist_mono, weight = FontWeight.Medium),
            Font(R.font.geist_mono, weight = FontWeight.SemiBold),
            Font(R.font.geist_mono, weight = FontWeight.Bold),
            Font(R.font.geist_mono, weight = FontWeight.ExtraBold),
        )
    }
}

private fun medtrackTypography(): Typography {
    val displayFamily = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        ManropeFontFamily
    } else {
        FontFamily.SansSerif
    }
    val bodyFamily = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        ManropeFontFamily
    } else {
        FontFamily.SansSerif
    }
    return Typography().withFontFamilies(displayFamily = displayFamily, bodyFamily = bodyFamily)
}

private fun Typography.withFontFamilies(displayFamily: FontFamily, bodyFamily: FontFamily): Typography =
    Typography(
        displayLarge = displayLarge.copy(fontFamily = displayFamily),
        displayMedium = displayMedium.copy(fontFamily = displayFamily),
        displaySmall = displaySmall.copy(fontFamily = displayFamily),
        headlineLarge = headlineLarge.copy(fontFamily = displayFamily),
        headlineMedium = headlineMedium.copy(fontFamily = displayFamily),
        headlineSmall = headlineSmall.copy(fontFamily = displayFamily),
        titleLarge = titleLarge.copy(fontFamily = displayFamily),
        titleMedium = titleMedium.copy(fontFamily = displayFamily),
        titleSmall = titleSmall.copy(fontFamily = displayFamily),
        bodyLarge = bodyLarge.copy(fontFamily = bodyFamily),
        bodyMedium = bodyMedium.copy(fontFamily = bodyFamily),
        bodySmall = bodySmall.copy(fontFamily = bodyFamily),
        labelLarge = labelLarge.copy(fontFamily = bodyFamily),
        labelMedium = labelMedium.copy(fontFamily = bodyFamily),
        labelSmall = labelSmall.copy(fontFamily = bodyFamily),
    )

@Composable
fun MedtrackTheme(
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = MedtrackLightColorScheme,
        typography = medtrackTypography(),
        content = content,
    )
}
