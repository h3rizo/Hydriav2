(function() {
    let planningPhotosDataGlobal = [];

    function getPhotoInput() {
        return document.getElementById('planning-photo-input');
    }

    function getPhotoJsonInput() {
        return document.getElementById('planning-photos-json');
    }

    function getPhotoGallery() {
        return document.getElementById('planning-photos-gallery');
    }

    function updatePlanningPhotosJSONGlobal() {
        const jsonInput = getPhotoJsonInput();
        if (jsonInput) {
            jsonInput.value = JSON.stringify(planningPhotosDataGlobal);
        }
    }

    function renderPlanningPhotosGalleryGlobal() {
        const gallery = getPhotoGallery();
        if (!gallery) return;

        if (!planningPhotosDataGlobal.length) {
            gallery.innerHTML = '<div class="col-span-full text-center text-gray-400 py-4"><i class="fas fa-images text-4xl mb-2"></i><br>Aucune photo ajoutee</div>';
            return;
        }

        gallery.innerHTML = planningPhotosDataGlobal.map(photo => `
            <div class="relative group">
                <img src="${photo.data}" alt="${photo.name}" class="w-full h-32 object-cover rounded-lg border-2 border-base-300">
                <button type="button" onclick="removePlanningPhoto('${photo.id}')"
                        class="absolute top-1 right-1 btn btn-xs btn-error btn-circle opacity-0 group-hover:opacity-100 transition-opacity">
                    <i class="fas fa-times"></i>
                </button>
                <div class="absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 text-white text-xs p-1 rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity">
                    ${(photo.size / 1024).toFixed(0)} KB
                </div>
            </div>
        `).join('');
    }

    function compressPlanningImageGlobal(file, callback) {
        const reader = new FileReader();

        reader.onload = function(e) {
            const img = new Image();
            img.onload = function() {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                const MAX_WIDTH = 1200;
                const MAX_HEIGHT = 1200;

                let width = img.width;
                let height = img.height;

                if (width > height && width > MAX_WIDTH) {
                    height = Math.round((height * MAX_WIDTH) / width);
                    width = MAX_WIDTH;
                } else if (height >= width && height > MAX_HEIGHT) {
                    width = Math.round((width * MAX_HEIGHT) / height);
                    height = MAX_HEIGHT;
                }

                canvas.width = width;
                canvas.height = height;
                ctx.drawImage(img, 0, 0, width, height);

                const compressedDataUrl = canvas.toDataURL('image/jpeg', 0.8);
                const compressedSize = Math.round((compressedDataUrl.length - 'data:image/jpeg;base64,'.length) * 3 / 4);
                callback(compressedDataUrl, compressedSize);
            };
            img.src = e.target.result;
        };

        reader.readAsDataURL(file);
    }

    window.selectPlanningPhoto = function() {
        const input = getPhotoInput();
        if (!input) return;
        input.removeAttribute('capture');
        input.click();
    };

    window.capturePlanningPhoto = function() {
        const input = getPhotoInput();
        if (!input) return;
        input.setAttribute('capture', 'environment');
        input.click();
    };

    window.handlePlanningPhotoSelected = function(event) {
        const files = event && event.target ? event.target.files : null;
        if (!files || files.length === 0) return;

        Array.from(files).forEach(file => {
            if (!file.type.startsWith('image/')) return;

            compressPlanningImageGlobal(file, function(compressedDataUrl, compressedSize) {
                planningPhotosDataGlobal.push({
                    id: Date.now() + Math.random(),
                    name: file.name,
                    data: compressedDataUrl,
                    size: compressedSize,
                    originalSize: file.size,
                    type: file.type,
                    date: new Date().toISOString()
                });
                renderPlanningPhotosGalleryGlobal();
                updatePlanningPhotosJSONGlobal();
            });
        });

        event.target.value = '';
        event.target.removeAttribute('capture');
    };

    window.removePlanningPhoto = function(photoId) {
        planningPhotosDataGlobal = planningPhotosDataGlobal.filter(p => String(p.id) !== String(photoId));
        renderPlanningPhotosGalleryGlobal();
        updatePlanningPhotosJSONGlobal();
    };

    document.addEventListener('DOMContentLoaded', function() {
        const jsonInput = getPhotoJsonInput();
        if (jsonInput && jsonInput.value && jsonInput.value.trim() !== '') {
            try {
                planningPhotosDataGlobal = JSON.parse(jsonInput.value);
            } catch (e) {
                planningPhotosDataGlobal = [];
            }
        }
        renderPlanningPhotosGalleryGlobal();
    });
})();
