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
import androidx.compose.ui.unit.sp

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

/**
 * The MEDTRACK type scale from tokens.source.json, expressed on the Material 3
 * slots the app already consumes. Manrope leans heavy, so 700/800 carry the
 * hierarchy; body never falls below 13sp on-device.
 *
 *   display  26/800   detail & hero patient name
 *   title    21/800   screen titles
 *   titleMd  18/800   home greeting
 *   card     16/800   list row / card name
 *   body     15/500   primary body & inputs
 *   sub      13.5/600 diagnosis / supporting line
 *   cap      12.5/700 metadata captions
 *   eyebrow  12.5/800 uppercase section labels
 */
private fun Typography.withFontFamilies(displayFamily: FontFamily, bodyFamily: FontFamily): Typography =
    Typography(
        displayLarge = displayLarge.copy(fontFamily = displayFamily, fontSize = 30.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.5).sp),
        displayMedium = displayMedium.copy(fontFamily = displayFamily, fontSize = 28.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.5).sp),
        displaySmall = displaySmall.copy(fontFamily = displayFamily, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 30.sp, letterSpacing = (-0.4).sp),
        headlineLarge = headlineLarge.copy(fontFamily = displayFamily, fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.4).sp),
        headlineMedium = headlineMedium.copy(fontFamily = displayFamily, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.4).sp),
        headlineSmall = headlineSmall.copy(fontFamily = displayFamily, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 25.sp, letterSpacing = (-0.3).sp),
        titleLarge = titleLarge.copy(fontFamily = displayFamily, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 25.sp, letterSpacing = (-0.3).sp),
        titleMedium = titleMedium.copy(fontFamily = displayFamily, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 22.sp, letterSpacing = (-0.2).sp),
        titleSmall = titleSmall.copy(fontFamily = displayFamily, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 20.sp, letterSpacing = (-0.2).sp),
        bodyLarge = bodyLarge.copy(fontFamily = bodyFamily, fontSize = 15.sp, fontWeight = FontWeight.Medium, lineHeight = 21.sp),
        bodyMedium = bodyMedium.copy(fontFamily = bodyFamily, fontSize = 14.sp, fontWeight = FontWeight.Medium, lineHeight = 19.sp),
        bodySmall = bodySmall.copy(fontFamily = bodyFamily, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, lineHeight = 18.sp),
        labelLarge = labelLarge.copy(fontFamily = bodyFamily, fontSize = 14.sp, fontWeight = FontWeight.Bold),
        labelMedium = labelMedium.copy(fontFamily = bodyFamily, fontSize = 12.5.sp, fontWeight = FontWeight.Bold),
        labelSmall = labelSmall.copy(fontFamily = bodyFamily, fontSize = 12.sp, fontWeight = FontWeight.ExtraBold),
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
