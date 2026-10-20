package mg.hydria.app

import org.junit.Assert.*
import org.junit.Test
import java.io.File
import kotlin.math.pow

/**
 * TRANSVERSE-03 : lit res/values/colors.xml (mode clair) et values-night/colors.xml pour garder les
 * contrastes « au soleil » sans appareil. Les accents servent aux remplissages ; tout texte coloré
 * par un ton utilise les jetons *_text. En sombre ces jetons valent l'accent : le rendu ne change pas.
 */
class ColorTokensContrastTest {
    private fun resFile(dir: String): File =
        listOf("src/main/res/$dir/colors.xml", "app/src/main/res/$dir/colors.xml").map(::File).first { it.exists() }

    private fun tokens(dir: String): Map<String, String> =
        Regex("""<color name="([a-z_]+)">(#[0-9A-Fa-f]{6})</color>""").findAll(resFile(dir).readText())
            .associate { it.groupValues[1] to it.groupValues[2].uppercase() }

    private val light = tokens("values")
    private val night = tokens("values-night")

    private fun channel(hex: String, index: Int): Double {
        val c = hex.substring(1 + index * 2, 3 + index * 2).toInt(16) / 255.0
        return if (c <= 0.03928) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
    }

    private fun luminance(hex: String) = 0.2126 * channel(hex, 0) + 0.7152 * channel(hex, 1) + 0.0722 * channel(hex, 2)

    private fun ratio(a: String, b: String): Double {
        val (hi, lo) = luminance(a).let { la -> luminance(b).let { lb -> if (la >= lb) la to lb else lb to la } }
        return (hi + 0.05) / (lo + 0.05)
    }

    /** Teinte d'une pastille : accent à alpha 35/255 sur la surface (voir HydriaUi.badge). */
    private fun tint(accent: String, surface: String, alpha: Double = 35 / 255.0): String {
        fun mix(i: Int) = (accent.substring(1 + i * 2, 3 + i * 2).toInt(16) * alpha + surface.substring(1 + i * 2, 3 + i * 2).toInt(16) * (1 - alpha)).toInt()
        return "#%02X%02X%02X".format(mix(0), mix(1), mix(2))
    }

    private val tones = listOf("cyan", "success", "warning", "vase", "error")

    @Test fun lightSecondaryAndMutedTextMeetTargetsOnEverySurface() {
        for (surface in listOf("hydria_surface", "hydria_background", "hydria_surface_raised")) {
            assertTrue("secondary sur $surface", ratio(light.getValue("hydria_text_secondary"), light.getValue(surface)) >= 7.0)
            assertTrue("muted sur $surface", ratio(light.getValue("hydria_text_muted"), light.getValue(surface)) >= 4.5)
        }
    }

    @Test fun lightToneTextTokensAreReadableOnSurfaceAndOnTheirOwnTint() {
        val surface = light.getValue("hydria_surface")
        for (tone in tones) {
            val text = light.getValue("hydria_${tone}_text")
            assertTrue("${tone}_text sur surface", ratio(text, surface) >= 6.5)
            val tinted = tint(light.getValue("hydria_$tone"), surface)
            assertTrue("${tone}_text sur sa teinte", ratio(text, tinted) >= 5.0)
        }
    }

    @Test fun lightFieldOutlineReachesThreeToOneOnEverySurface() {
        // WCAG 1.4.11 : le contour d'un champ (posé sur la surface, le fond ou la surface relevée) fait au moins 3:1.
        // L'ancien #7F9AA4 donnait 2,97 / 2,80 / 2,76:1 ; avant lui le contour valait 1,35:1.
        for (surface in listOf("hydria_surface", "hydria_surface_raised", "hydria_background")) {
            assertTrue("field_outline sur $surface", ratio(light.getValue("hydria_field_outline"), light.getValue(surface)) >= 3.0)
        }
        assertTrue(ratio(light.getValue("hydria_outline"), light.getValue("hydria_surface")) < 2.0)
    }

    @Test fun nightToneTextTokensEqualTheAccentSoDarkRenderingIsUnchanged() {
        for (tone in tones) assertEquals(tone, night.getValue("hydria_$tone"), night.getValue("hydria_${tone}_text"))
        assertEquals(night.getValue("hydria_outline"), night.getValue("hydria_field_outline"))
    }

    @Test fun everyTokenExistsInBothModes() {
        val names = tones.map { "hydria_${it}_text" } + "hydria_field_outline"
        for (name in names) {
            assertTrue("clair: $name", name in light)
            assertTrue("sombre: $name", name in night)
        }
        // Le mode sombre ne définit pas de jeton absent du mode clair.
        assertTrue(night.keys.all { it in light })
    }
}
