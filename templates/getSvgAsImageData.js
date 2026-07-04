function getSvgAsImageData(format) {
    return new Promise((resolve, reject) => {
        try {
            const svgElement = document.querySelector('#container svg');
            if (!svgElement) {
                return resolve('');
            }
            
            let width = svgElement.viewBox.baseVal.width || svgElement.clientWidth || 800;
            let height = svgElement.viewBox.baseVal.height || svgElement.clientHeight || 600;
            
            const parser = new DOMParser();
            const doc = parser.parseFromString(window.rawSvg, 'image/svg+xml');
            const cleanSvg = doc.documentElement;
            
            cleanSvg.setAttribute('width', width);
            cleanSvg.setAttribute('height', height);
            
            const svgString = new XMLSerializer().serializeToString(cleanSvg);
            const svgBlob = new Blob([svgString], {type: 'image/svg+xml;charset=utf-8'});
            const url = URL.createObjectURL(svgBlob);
            
            const img = new Image();
            img.onload = function() {
                try {
                    const canvas = document.createElement('canvas');
                    const scale = 3.0;
                    canvas.width = width * scale;
                    canvas.height = height * scale;
                    
                    const ctx = canvas.getContext('2d');
                    ctx.scale(scale, scale);
                    
                    if (format === 'image/jpeg') {
                        ctx.fillStyle = '#ffffff';
                        ctx.fillRect(0, 0, width, height);
                    }
                    
                    ctx.drawImage(img, 0, 0);
                    URL.revokeObjectURL(url);
                    
                    const dataUrl = canvas.toDataURL(format, 0.95);
                    resolve(dataUrl);
                } catch(err) {
                    reject(err);
                }
            };
            img.onerror = function(err) {
                reject(err);
            };
            img.src = url;
        } catch(e) {
            reject(e);
        }
    });
}
