export class HudScene extends Phaser.Scene {
    constructor() {
        super({ key: 'HudScene', active: false });
    }

    create() {
        this.eventBus = this.registry.get('eventBus');

        this.add.rectangle(640, 42, 1220, 72, 0x07131d, 0.82)
            .setStrokeStyle(1, 0x67e8f9, 0.42)
            .setScrollFactor(0);
        this.add.rectangle(640, 22, 1216, 10, 0x67e8f9, 0.08).setScrollFactor(0);

        this.scoreText = this.makeHudText(70, 20, 'Score: 0');
        this.satisfactionText = this.makeHudText(260, 20, 'Satisfaction: 100');
        this.breakdownsText = this.makeHudText(520, 20, 'Pannes: 0');
        this.paymentsText = this.makeHudText(710, 20, 'Paiements: 0');
        this.timerText = this.makeHudText(980, 20, 'Temps: 0');
        this.objectiveText = this.makeHudText(70, 48, '');

        this.feedBackground = this.add.rectangle(1080, 570, 340, 230, 0x081420, 0.88)
            .setStrokeStyle(1, 0x22d3ee, 0.4)
            .setScrollFactor(0);
        this.add.rectangle(1080, 468, 332, 28, 0x0f2b3e, 0.8).setScrollFactor(0);
        this.feedTitle = this.add.text(930, 460, 'Journal terrain', {
            fontFamily: 'Verdana',
            fontSize: '18px',
            color: '#a5f3fc',
            fontStyle: 'bold',
        }).setScrollFactor(0);
        this.feedLines = [];
        for (let index = 0; index < 6; index += 1) {
            this.feedLines.push(
                this.add.text(930, 492 + (index * 28), '', {
                    fontFamily: 'Verdana',
                    fontSize: '14px',
                    color: '#e2e8f0',
                    wordWrap: { width: 290 },
                }).setScrollFactor(0)
            );
        }

        this.facilityPanel = this.add.rectangle(210, 590, 340, 250, 0x081420, 0.9)
            .setStrokeStyle(1, 0x34d399, 0.4)
            .setScrollFactor(0);
        this.add.rectangle(210, 468, 332, 28, 0x0d2d28, 0.8).setScrollFactor(0);
        this.facilityTitle = this.add.text(60, 470, 'Ouvrages', {
            fontFamily: 'Verdana',
            fontSize: '18px',
            color: '#a7f3d0',
            fontStyle: 'bold',
        }).setScrollFactor(0);
        this.facilityLines = [];
        for (let index = 0; index < 4; index += 1) {
            this.facilityLines.push(
                this.add.text(60, 505 + (index * 48), '', {
                    fontFamily: 'Verdana',
                    fontSize: '14px',
                    color: '#d1fae5',
                    wordWrap: { width: 280 },
                }).setScrollFactor(0)
            );
        }

        this.banner = this.add.text(640, 110, '', {
            fontFamily: 'Verdana',
            fontSize: '28px',
            color: '#fef3c7',
            backgroundColor: 'rgba(8,20,32,0.9)',
            padding: { left: 20, right: 20, top: 12, bottom: 12 },
        }).setOrigin(0.5).setScrollFactor(0).setVisible(false);

        this.eventBus.on('hud:update', this.renderHud, this);
        this.eventBus.on('hud:end', this.showEndBanner, this);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            this.eventBus.off('hud:update', this.renderHud, this);
            this.eventBus.off('hud:end', this.showEndBanner, this);
        });
    }

    makeHudText(x, y, text) {
        return this.add.text(x, y, text, {
            fontFamily: 'Verdana',
            fontSize: '20px',
            color: '#ecfeff',
            fontStyle: 'bold',
            shadow: {
                offsetX: 0,
                offsetY: 1,
                color: '#020617',
                blur: 6,
                fill: true,
            },
        }).setScrollFactor(0);
    }

    renderHud(payload) {
        this.scoreText.setText(`Score: ${payload.score}`);
        this.satisfactionText.setText(`Satisfaction: ${payload.satisfaction}`);
        this.breakdownsText.setText(`Pannes: ${payload.pendingBreakdowns}`);
        this.paymentsText.setText(`Paiements: ${payload.pendingPayments}`);
        this.timerText.setText(`Temps: ${payload.timeLeft}s`);
        this.objectiveText.setText(`Mission: score >= ${payload.minVictoryScore} et prioriser le multi-sites`);

        this.feedLines.forEach((line, index) => {
            line.setText(payload.feed[index] || '');
        });

        this.facilityLines.forEach((line, index) => {
            const facility = payload.facilities[index];
            if (!facility) {
                line.setText('');
                return;
            }
            const label = facility.state === 'healthy'
                ? 'OK'
                : facility.state === 'broken'
                    ? 'PANNE'
                    : 'REPARATION';
            line.setText(`${facility.name}\nEtat: ${label}`);
            line.setColor(
                facility.state === 'healthy'
                    ? '#d1fae5'
                    : facility.state === 'broken'
                        ? '#fdba74'
                        : '#fde68a'
            );
        });
    }

    showEndBanner(payload) {
        this.banner.setText(
            payload.status === 'victory'
                ? `Mission reussie - ${payload.reason}`
                : `Mission echouee - ${payload.reason}`
        );
        this.banner.setColor(payload.status === 'victory' ? '#bbf7d0' : '#fecaca');
        this.banner.setVisible(true);
    }
}
