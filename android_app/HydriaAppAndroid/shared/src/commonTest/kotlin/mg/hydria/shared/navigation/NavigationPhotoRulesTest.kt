package mg.hydria.shared.navigation

import kotlin.test.*

class NavigationPhotoRulesTest {
    @Test fun decodingSampleUsesPowersOfTwoAndBothDimensions() {
        assertEquals(1,NavigationPhotoRules.sampleSize(1600,1200))
        assertEquals(2,NavigationPhotoRules.sampleSize(1601,1200))
        assertEquals(4,NavigationPhotoRules.sampleSize(1200,6400))
        assertEquals(4,NavigationPhotoRules.sampleSize(4032,3024))
    }
    @Test fun resizePreservesOrientationDoesNotUpscaleAndKeepsOnePixelMinimum() {
        assertEquals(PhotoDimensions(1280,960,true),NavigationPhotoRules.dimensions(1600,1200))
        assertEquals(PhotoDimensions(960,1280,true),NavigationPhotoRules.dimensions(1200,1600))
        assertEquals(PhotoDimensions(1280,720,false),NavigationPhotoRules.dimensions(1280,720))
        assertEquals(PhotoDimensions(100,100,false),NavigationPhotoRules.dimensions(100,100))
        assertEquals(PhotoDimensions(1,1280,true),NavigationPhotoRules.dimensions(1,10000))
    }
    @Test fun exactSizeLimitIsAcceptedAndOverflowKeepsErrorMessage() {
        NavigationPhotoRules.checkSize(NavigationPhotoRules.MAX_BYTES)
        val failure = assertFailsWith<IllegalStateException> {
            NavigationPhotoRules.checkSize(NavigationPhotoRules.MAX_BYTES + 1)
        }
        assertEquals("Photo trop volumineuse",failure.message)
        assertEquals(80,NavigationPhotoRules.JPEG_QUALITY)
    }
}
