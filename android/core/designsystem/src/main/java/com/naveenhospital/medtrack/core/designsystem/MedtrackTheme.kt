package com.naveenhospital.medtrack.core.designsystem

import android.os.Build
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily

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

private val RobotoFlexFontFamily by lazy {
    FontFamily(Font(R.font.roboto_flex_variable))
}

private fun medtrackTypography(): Typography =
    Typography().withFontFamily(
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            RobotoFlexFontFamily
        } else {
            FontFamily.SansSerif
        },
    )

private fun Typography.withFontFamily(fontFamily: FontFamily): Typography =
    Typography(
        displayLarge = displayLarge.copy(fontFamily = fontFamily),
        displayMedium = displayMedium.copy(fontFamily = fontFamily),
        displaySmall = displaySmall.copy(fontFamily = fontFamily),
        headlineLarge = headlineLarge.copy(fontFamily = fontFamily),
        headlineMedium = headlineMedium.copy(fontFamily = fontFamily),
        headlineSmall = headlineSmall.copy(fontFamily = fontFamily),
        titleLarge = titleLarge.copy(fontFamily = fontFamily),
        titleMedium = titleMedium.copy(fontFamily = fontFamily),
        titleSmall = titleSmall.copy(fontFamily = fontFamily),
        bodyLarge = bodyLarge.copy(fontFamily = fontFamily),
        bodyMedium = bodyMedium.copy(fontFamily = fontFamily),
        bodySmall = bodySmall.copy(fontFamily = fontFamily),
        labelLarge = labelLarge.copy(fontFamily = fontFamily),
        labelMedium = labelMedium.copy(fontFamily = fontFamily),
        labelSmall = labelSmall.copy(fontFamily = fontFamily),
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
