import { getGameConfig } from './config.js';
import { BootScene } from './scenes/BootScene.js';
import { GameScene } from './scenes/GameScene.js';
import { HudScene } from './scenes/HudScene.js';

const root = document.getElementById('serious-game-root');

function renderFallback(message) {
    if (!root) {
        return;
    }
    root.innerHTML = `
        <div style="
            min-height: 720px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            color: #e2e8f0;
            text-align: center;
            font-family: Verdana, sans-serif;
            background: radial-gradient(circle at top, rgba(34,211,238,0.12), transparent 35%), linear-gradient(180deg, #07131d 0%, #10283a 100%);
        ">
            <div>
                <div style="font-size: 1.5rem; font-weight: 700; margin-bottom: 0.75rem;">Hydria Academy</div>
                <div style="font-size: 1rem; opacity: 0.92;">${message}</div>
            </div>
        </div>
    `;
}

if (root && window.Phaser) {
    try {
        window.__hydriaSeriousGameBooted = true;
        root.innerHTML = '';
        const gameConfig = getGameConfig(root);
        const eventBus = new Phaser.Events.EventEmitter();

        const phaserGame = new Phaser.Game({
            type: Phaser.AUTO,
            parent: root,
            width: gameConfig.width,
            height: gameConfig.height,
            backgroundColor: '#0b1f30',
            physics: {
                default: 'arcade',
                arcade: {
                    gravity: { y: 0 },
                    debug: false,
                },
            },
            scale: {
                mode: Phaser.Scale.FIT,
                autoCenter: Phaser.Scale.CENTER_BOTH,
            },
            scene: [BootScene, GameScene, HudScene],
        });

        phaserGame.registry.set('eventBus', eventBus);
        phaserGame.scene.start('BootScene', { gameConfig });
    } catch (error) {
        console.error('Hydria Academy failed to start:', error);
        renderFallback("Le jeu n'a pas pu demarrer. Ouvrez la console du navigateur pour voir l'erreur JavaScript.");
    }
} else if (root) {
    renderFallback("Phaser n'a pas ete charge. Verifiez le chargement du script CDN ou integrez Phaser localement.");
}
