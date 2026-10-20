export class BootScene extends Phaser.Scene {
    constructor() {
        super({ key: 'BootScene' });
    }

    init(data) {
        this.gameConfig = data.gameConfig;
    }

    preload() {
        this.createTextureFromGraphics('player', (graphics) => {
            graphics.fillStyle(0x020617, 0.2);
            graphics.fillEllipse(32, 58, 30, 10);
            graphics.fillStyle(0x1d4ed8, 1);
            graphics.fillTriangle(32, 6, 15, 34, 49, 34);
            graphics.fillStyle(0xf8fafc, 1);
            graphics.fillCircle(32, 15, 8);
            graphics.fillStyle(0x0f172a, 1);
            graphics.fillCircle(29, 14, 1.4);
            graphics.fillCircle(35, 14, 1.4);
            graphics.fillStyle(0xf59e0b, 1);
            graphics.fillRect(24, 24, 16, 6);
            graphics.fillStyle(0x60a5fa, 1);
            graphics.fillTriangle(18, 28, 10, 42, 22, 40);
            graphics.fillTriangle(46, 28, 42, 40, 54, 42);
            graphics.fillStyle(0x1e293b, 1);
            graphics.fillTriangle(28, 32, 22, 58, 30, 58);
            graphics.fillTriangle(36, 32, 34, 58, 42, 58);
        }, 64, 64);

        this.createTextureFromGraphics('facility', (graphics) => {
            graphics.fillStyle(0x020617, 0.18);
            graphics.fillEllipse(72, 132, 110, 22);
            graphics.fillStyle(0x0f766e, 1);
            graphics.beginPath();
            graphics.moveTo(72, 12);
            graphics.lineTo(124, 42);
            graphics.lineTo(72, 72);
            graphics.lineTo(20, 42);
            graphics.closePath();
            graphics.fillPath();
            graphics.fillStyle(0x14b8a6, 1);
            graphics.fillTriangle(72, 14, 118, 42, 72, 67);
            graphics.fillStyle(0x115e59, 1);
            graphics.fillTriangle(72, 14, 72, 67, 24, 42);
            graphics.fillStyle(0xe2e8f0, 0.96);
            graphics.fillRect(30, 42, 84, 54);
            graphics.fillStyle(0xcbd5e1, 0.95);
            graphics.fillTriangle(30, 42, 72, 20, 114, 42);
            graphics.fillStyle(0x334155, 1);
            graphics.fillRect(63, 60, 18, 36);
            graphics.fillStyle(0x67e8f9, 0.9);
            graphics.fillRect(42, 56, 12, 14);
            graphics.fillRect(90, 56, 12, 14);
            graphics.lineStyle(4, 0x93c5fd, 0.9);
            graphics.beginPath();
            graphics.moveTo(8, 108);
            graphics.lineTo(136, 108);
            graphics.strokePath();
        }, 144, 144);

        this.createTextureFromGraphics('citizen', (graphics) => {
            graphics.fillStyle(0x020617, 0.16);
            graphics.fillEllipse(26, 52, 22, 8);
            graphics.fillStyle(0xfdba74, 1);
            graphics.fillCircle(26, 15, 8);
            graphics.fillStyle(0x475569, 1);
            graphics.fillTriangle(26, 22, 12, 46, 40, 46);
            graphics.fillStyle(0x94a3b8, 1);
            graphics.fillTriangle(18, 34, 8, 46, 18, 44);
            graphics.fillTriangle(34, 34, 34, 44, 44, 46);
            graphics.fillStyle(0x1e293b, 1);
            graphics.fillTriangle(22, 44, 18, 60, 25, 60);
            graphics.fillTriangle(30, 44, 27, 60, 34, 60);
        }, 52, 64);

        this.createTextureFromGraphics('tree', (graphics) => {
            graphics.fillStyle(0x020617, 0.15);
            graphics.fillEllipse(30, 54, 34, 10);
            graphics.fillStyle(0x854d0e, 1);
            graphics.fillRect(26, 32, 8, 20);
            graphics.fillStyle(0x166534, 1);
            graphics.fillTriangle(30, 6, 12, 28, 48, 28);
            graphics.fillStyle(0x22c55e, 0.94);
            graphics.fillTriangle(30, 14, 14, 34, 46, 34);
            graphics.fillStyle(0x4ade80, 0.9);
            graphics.fillTriangle(30, 20, 16, 38, 44, 38);
        }, 60, 64);

        this.createTextureFromGraphics('rock', (graphics) => {
            graphics.fillStyle(0x0f172a, 0.16);
            graphics.fillEllipse(24, 32, 34, 10);
            graphics.fillStyle(0x94a3b8, 1);
            graphics.fillRoundedRect(6, 10, 36, 20, 8);
            graphics.lineStyle(2, 0xe2e8f0, 0.45);
            graphics.strokeRoundedRect(6, 10, 36, 20, 8);
        }, 48, 40);

        this.createTextureFromGraphics('house', (graphics) => {
            graphics.fillStyle(0x020617, 0.16);
            graphics.fillEllipse(34, 56, 42, 12);
            graphics.fillStyle(0xe7e5e4, 1);
            graphics.fillTriangle(34, 16, 10, 30, 34, 44);
            graphics.fillTriangle(34, 16, 34, 44, 58, 30);
            graphics.fillStyle(0xb45309, 1);
            graphics.fillTriangle(34, 4, 8, 20, 34, 34);
            graphics.fillStyle(0x92400e, 1);
            graphics.fillTriangle(34, 4, 34, 34, 60, 20);
            graphics.fillStyle(0x334155, 1);
            graphics.fillRect(29, 28, 10, 16);
        }, 68, 64);
    }

    createTextureFromGraphics(key, drawFn, width, height) {
        const graphics = this.make.graphics({ x: 0, y: 0, add: false });
        drawFn(graphics);
        graphics.generateTexture(key, width, height);
        graphics.destroy();
    }

    create() {
        this.scene.start('GameScene', { gameConfig: this.gameConfig });
    }
}
