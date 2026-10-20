import { Player } from '../entities/Player.js';
import { GameState, CITIZEN_STATE, FACILITY_STATE } from '../systems/GameState.js';

export class GameScene extends Phaser.Scene {
    constructor() {
        super({ key: 'GameScene' });
    }

    init(data) {
        this.gameConfig = data.gameConfig;
    }

    create() {
        this.eventBus = this.registry.get('eventBus');
        this.state = new GameState(this.gameConfig);
        this.registry.set('gameState', this.state);
        this.facilityViews = [];
        this.citizenViews = [];
        this.finished = false;
        this.districtCards = [];
        this.decorAnimations = [];

        this.createWorld();
        this.createActors();
        this.createCamera();
        this.createInput();
        this.scene.launch('HudScene');
        this.refreshHud();
    }

    createWorld() {
        this.physics.world.setBounds(0, 0, this.gameConfig.worldWidth, this.gameConfig.worldHeight);

        this.add.rectangle(1200, 700, 2400, 1400, 0x0a1822);
        this.add.rectangle(1200, 700, 2400, 1400, 0x163042, 0.18);

        this.drawIsoGround();
        this.drawTerrainPatches();
        this.drawWaterNetwork();
        this.drawDistricts();
        this.drawRoads();
        this.drawDecor();
        this.drawWorldTitle();
    }

    drawIsoGround() {
        const graphics = this.add.graphics();
        const tileW = 120;
        const tileH = 60;
        const cols = 24;
        const rows = 14;
        const originX = 1200;
        const originY = 140;

        for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < cols; col += 1) {
                const x = originX + ((col - row) * (tileW / 2));
                const y = originY + ((col + row) * (tileH / 2));
                const green = Phaser.Math.Between(0x365f2c, 0x557b34);
                const alpha = 0.11 + ((col + row) % 3) * 0.02;
                graphics.fillStyle(green, alpha);
                graphics.beginPath();
                graphics.moveTo(x, y);
                graphics.lineTo(x + tileW / 2, y + tileH / 2);
                graphics.lineTo(x, y + tileH);
                graphics.lineTo(x - tileW / 2, y + tileH / 2);
                graphics.closePath();
                graphics.fillPath();
                graphics.lineStyle(1, 0xffffff, 0.018);
                graphics.strokePath();
            }
        }
    }

    drawTerrainPatches() {
        const patches = [
            { x: 360, y: 240, w: 520, h: 300, color: 0x1f4d3a, alpha: 0.24 },
            { x: 1160, y: 710, w: 720, h: 420, color: 0x284d2f, alpha: 0.22 },
            { x: 1840, y: 990, w: 560, h: 320, color: 0x433724, alpha: 0.2 },
            { x: 2080, y: 360, w: 420, h: 260, color: 0x3b2f56, alpha: 0.18 },
        ];

        patches.forEach((patch) => {
            this.add.rectangle(patch.x, patch.y, patch.w, patch.h, patch.color, patch.alpha)
                .setStrokeStyle(2, 0xffffff, 0.04);
        });

        for (let i = 0; i < 220; i += 1) {
            const x = Phaser.Math.Between(20, this.gameConfig.worldWidth - 20);
            const y = Phaser.Math.Between(20, this.gameConfig.worldHeight - 20);
            const radius = Phaser.Math.Between(2, 6);
            const alpha = Phaser.Math.FloatBetween(0.04, 0.12);
            const tint = Phaser.Utils.Array.GetRandom([0x6ee7b7, 0xa3e635, 0x22c55e, 0xfde68a]);
            this.add.circle(x, y, radius, tint, alpha);
        }
    }

    drawWaterNetwork() {
        const shadow = this.add.graphics();
        const mainChannel = new Phaser.Curves.Path(140, 160);
        mainChannel.cubicBezierTo(380, 220, 620, 280, 900, 460);
        mainChannel.cubicBezierTo(1180, 620, 1500, 740, 2140, 940);

        shadow.lineStyle(30, 0x020617, 0.22);
        mainChannel.draw(shadow, 96);

        const riverBase = this.add.graphics();
        riverBase.lineStyle(22, 0x1d4ed8, 0.30);
        mainChannel.draw(riverBase, 96);

        const riverGlow = this.add.graphics();
        riverGlow.lineStyle(10, 0x67e8f9, 0.46);
        mainChannel.draw(riverGlow, 96);

        const branches = this.add.graphics();
        branches.lineStyle(10, 0x67e8f9, 0.35);
        branches.beginPath();
        branches.moveTo(860, 460);
        branches.lineTo(840, 260);
        branches.moveTo(1180, 650);
        branches.lineTo(1600, 320);
        branches.moveTo(1360, 760);
        branches.lineTo(1880, 1080);
        branches.strokePath();

        const shimmerPoints = mainChannel.getSpacedPoints(40);
        this.waterShimmers = shimmerPoints.map((point, index) => {
            const shimmer = this.add.ellipse(point.x, point.y, 34, 10, 0xe0f2fe, 0.08);
            this.tweens.add({
                targets: shimmer,
                alpha: { from: 0.03, to: 0.16 },
                scaleX: { from: 0.85, to: 1.2 },
                scaleY: { from: 0.85, to: 1.15 },
                duration: 1400 + (index * 35),
                yoyo: true,
                repeat: -1,
                delay: index * 90,
            });
            return shimmer;
        });
    }

    drawDistricts() {
        const districts = [
            { x: 520, y: 320, w: 520, h: 340, color: 0x155e75, label: 'District Nord' },
            { x: 1220, y: 660, w: 620, h: 380, color: 0x166534, label: 'District Centre' },
            { x: 1850, y: 980, w: 520, h: 300, color: 0x7c2d12, label: 'District Sud' },
            { x: 2080, y: 380, w: 420, h: 300, color: 0x5b21b6, label: 'District Est' },
        ];

        districts.forEach((zone) => {
            const body = this.add.graphics();
            body.fillStyle(zone.color, 0.18);
            body.lineStyle(2, 0xcbd5e1, 0.12);
            body.beginPath();
            body.moveTo(zone.x, zone.y - zone.h / 2);
            body.lineTo(zone.x + zone.w / 2, zone.y);
            body.lineTo(zone.x, zone.y + zone.h / 2);
            body.lineTo(zone.x - zone.w / 2, zone.y);
            body.closePath();
            body.fillPath();
            body.strokePath();

            const ribbon = this.add.rectangle(zone.x, zone.y - (zone.h / 2) + 34, zone.w * 0.62, 42, 0x082032, 0.56)
                .setAngle(-12)
                .setStrokeStyle(1, 0xffffff, 0.08);
            const label = this.add.text(zone.x - (zone.w * 0.28), zone.y - (zone.h / 2) + 12, zone.label, {
                fontFamily: 'Verdana',
                fontSize: '22px',
                color: '#e0f2fe',
                fontStyle: 'bold',
                backgroundColor: '#0f172a88',
                padding: { left: 10, right: 10, top: 6, bottom: 6 },
            }).setAngle(-12);
            this.districtCards.push({ body, ribbon, label });
        });
    }

    drawRoads() {
        const roads = [
            { x: 1160, y: 680, w: 1540, h: 42, angle: -18 },
            { x: 1160, y: 680, w: 42, h: 860, angle: 18 },
            { x: 1880, y: 500, w: 500, h: 30, angle: -18 },
            { x: 760, y: 500, w: 580, h: 30, angle: -18 },
            { x: 1760, y: 980, w: 320, h: 30, angle: -18 },
        ];
        roads.forEach((road) => {
            this.add.rectangle(road.x, road.y, road.w, road.h, 0x9ca3af, 0.95)
                .setAngle(road.angle)
                .setStrokeStyle(2, 0xe2e8f0, 0.2);
        });

        const laneMarks = this.add.graphics();
        laneMarks.lineStyle(4, 0xf8fafc, 0.35);
        [
            [440, 680, 1880, 680],
            [1160, 250, 1160, 1100],
        ].forEach(([x1, y1, x2, y2]) => {
            for (let t = 0; t < 1; t += 0.06) {
                const sx = Phaser.Math.Linear(x1, x2, t);
                const sy = Phaser.Math.Linear(y1, y2, t);
                const ex = Phaser.Math.Linear(x1, x2, t + 0.03);
                const ey = Phaser.Math.Linear(y1, y2, t + 0.03);
                laneMarks.beginPath();
                laneMarks.moveTo(sx, sy);
                laneMarks.lineTo(ex, ey);
                laneMarks.strokePath();
            }
        });
    }

    drawDecor() {
        const trees = [
            [190, 260], [280, 980], [620, 180], [780, 930], [980, 190], [1480, 180],
            [1670, 1230], [2080, 180], [2240, 760], [2240, 1160], [420, 520], [1910, 210],
        ];
        trees.forEach(([x, y], index) => {
            const tree = this.add.image(x, y, 'tree').setAlpha(0.92);
            this.tweens.add({
                targets: tree,
                angle: { from: -1.2, to: 1.2 },
                duration: 2200 + (index * 70),
                yoyo: true,
                repeat: -1,
                ease: 'Sine.inOut',
            });
        });

        const rocks = [
            [340, 620], [540, 1110], [910, 840], [1320, 180], [1560, 950], [1980, 1240], [2180, 560],
        ];
        rocks.forEach(([x, y]) => this.add.image(x, y, 'rock').setAlpha(0.9));

        const houses = [
            [680, 300], [740, 360], [1540, 860], [1610, 920], [1950, 760], [2050, 840],
        ];
        houses.forEach(([x, y]) => {
            const shadow = this.add.ellipse(x, y + 28, 44, 14, 0x020617, 0.16);
            const house = this.add.image(x, y, 'house');
            this.decorAnimations.push({ shadow, house });
        });
    }

    drawWorldTitle() {
        this.add.text(60, 70, 'Hydria Academy - reseau multi-sites', {
            fontFamily: 'Verdana',
            fontSize: '32px',
            color: '#a5f3fc',
            fontStyle: 'bold',
            backgroundColor: '#082032aa',
            padding: { left: 12, right: 12, top: 8, bottom: 8 },
        });
        this.add.text(62, 118, 'Vue strategique: ouvrages, usagers, paiements et incidents en temps reel', {
            fontFamily: 'Verdana',
            fontSize: '17px',
            color: '#dbeafe',
            backgroundColor: '#08203288',
            padding: { left: 10, right: 10, top: 5, bottom: 5 },
        });
    }

    createActors() {
        this.player = new Player(this, 180, 680);

        this.state.facilities.forEach((facility) => {
            const halo = this.add.circle(facility.x, facility.y + 18, 96, 0x67e8f9, 0.08);
            const ring = this.add.circle(facility.x, facility.y + 20, 84, 0x000000, 0).setStrokeStyle(2, 0x67e8f9, 0.14);
            const sprite = this.physics.add.staticImage(facility.x, facility.y, 'facility');
            const label = this.add.text(facility.x - 82, facility.y - 118, facility.name, {
                fontFamily: 'Verdana',
                fontSize: '18px',
                color: '#f0fdfa',
                backgroundColor: '#082f49cc',
                padding: { left: 8, right: 8, top: 5, bottom: 5 },
            });
            const status = this.add.text(facility.x - 78, facility.y + 92, 'Operationnel', {
                fontFamily: 'Verdana',
                fontSize: '15px',
                color: '#bbf7d0',
                backgroundColor: '#111827d9',
                padding: { left: 8, right: 8, top: 4, bottom: 4 },
            });
            const marker = this.add.circle(facility.x + 82, facility.y - 78, 13, 0x22c55e, 1)
                .setStrokeStyle(3, 0xffffff, 0.25);
            this.tweens.add({
                targets: [halo, ring],
                scaleX: { from: 0.96, to: 1.05 },
                scaleY: { from: 0.96, to: 1.05 },
                duration: 1700,
                yoyo: true,
                repeat: -1,
                ease: 'Sine.inOut',
            });
            this.tweens.add({
                targets: marker,
                scale: { from: 0.95, to: 1.12 },
                duration: 800,
                yoyo: true,
                repeat: -1,
            });
            this.facilityViews.push({ facility, sprite, label, status, marker, halo, ring });
        });

        this.state.citizens.forEach((citizen, index) => {
            const facility = this.state.getFacilityById(citizen.facilityId);
            const citizenIndex = this.state.getCitizensForFacility(citizen.facilityId).findIndex((item) => item.id === citizen.id);
            const side = citizenIndex % 2 === 0 ? -1 : 1;
            const row = Math.floor(citizenIndex / 2);
            const x = facility.x + (side * (110 + (row * 14)));
            const y = facility.y + 126 + (row * 36);
            const sprite = this.physics.add.staticSprite(x, y, 'citizen');
            const label = this.add.text(x - 32, y - 56, citizen.name, {
                fontFamily: 'Verdana',
                fontSize: '14px',
                color: '#f8fafc',
                backgroundColor: '#0f172acc',
                padding: { left: 6, right: 6, top: 3, bottom: 3 },
            });
            const status = this.add.text(x - 54, y + 34, 'A payer', {
                fontFamily: 'Verdana',
                fontSize: '13px',
                color: '#fde68a',
                backgroundColor: '#111827d9',
                padding: { left: 6, right: 6, top: 3, bottom: 3 },
            });
            const marker = this.add.circle(x + 34, y - 30, 9, 0xeab308, 1)
                .setStrokeStyle(2, 0xffffff, 0.22);
            this.tweens.add({
                targets: marker,
                alpha: { from: 0.55, to: 1 },
                duration: 900 + (index * 30),
                yoyo: true,
                repeat: -1,
            });
            this.citizenViews.push({ citizen, sprite, label, status, marker });
        });
    }

    createCamera() {
        this.cameras.main.setBounds(0, 0, this.gameConfig.worldWidth, this.gameConfig.worldHeight);
        this.cameras.main.startFollow(this.player.sprite, true, 0.08, 0.08);
        this.cameras.main.setZoom(0.9);
        this.cameras.main.setRoundPixels(true);
    }

    createInput() {
        this.cursors = this.input.keyboard.createCursorKeys();
        this.keys = this.input.keyboard.addKeys({
            A: Phaser.Input.Keyboard.KeyCodes.A,
            D: Phaser.Input.Keyboard.KeyCodes.D,
            W: Phaser.Input.Keyboard.KeyCodes.W,
            S: Phaser.Input.Keyboard.KeyCodes.S,
            E: Phaser.Input.Keyboard.KeyCodes.E,
            ENTER: Phaser.Input.Keyboard.KeyCodes.ENTER,
            SPACE: Phaser.Input.Keyboard.KeyCodes.SPACE,
        });
        this.helperText = this.add.text(40, 720, 'Deplacement libre sur la carte. Action: Espace, Entree ou E.', {
            fontFamily: 'Verdana',
            fontSize: '18px',
            color: '#dbeafe',
            backgroundColor: '#082032dd',
            padding: { left: 12, right: 12, top: 8, bottom: 8 },
        }).setScrollFactor(0);
        this.interactionText = this.add.text(40, 756, '', {
            fontFamily: 'Verdana',
            fontSize: '20px',
            color: '#fef3c7',
            backgroundColor: '#111827e6',
            padding: { left: 12, right: 12, top: 8, bottom: 8 },
        }).setScrollFactor(0);
    }

    update(_, delta) {
        const deltaSeconds = delta / 1000;
        this.player.update(this.cursors, this.keys);
        this.state.tick(deltaSeconds);
        this.updateFacilityViews();
        this.updateCitizenViews();
        this.handleInteractionPrompt();
        this.checkEndState();
        this.refreshHud();
    }

    updateFacilityViews() {
        this.facilityViews.forEach((entry) => {
            if (entry.facility.state === FACILITY_STATE.BROKEN) {
                entry.sprite.setTint(0xfb923c);
                entry.status.setText('Panne critique');
                entry.status.setColor('#fdba74');
                entry.marker.setFillStyle(0xef4444, 1);
                entry.halo.setFillStyle(0xef4444, 0.1);
                entry.ring.setStrokeStyle(3, 0xef4444, 0.28);
            } else if (entry.facility.state === FACILITY_STATE.REPAIRING) {
                entry.sprite.setTint(0xfacc15);
                entry.status.setText('Equipe en reparation');
                entry.status.setColor('#fde68a');
                entry.marker.setFillStyle(0xfacc15, 1);
                entry.halo.setFillStyle(0xfacc15, 0.1);
                entry.ring.setStrokeStyle(3, 0xfacc15, 0.26);
            } else {
                entry.sprite.clearTint();
                entry.status.setText('Operationnel');
                entry.status.setColor('#bbf7d0');
                entry.marker.setFillStyle(0x22c55e, 1);
                entry.halo.setFillStyle(0x67e8f9, 0.08);
                entry.ring.setStrokeStyle(2, 0x67e8f9, 0.14);
            }
        });
    }

    updateCitizenViews() {
        this.citizenViews.forEach((entry) => {
            if (entry.citizen.state === CITIZEN_STATE.DUE) {
                entry.status.setText('Paiement attendu');
                entry.status.setColor('#fde68a');
                entry.marker.setFillStyle(0xeab308, 1);
            } else if (entry.citizen.state === CITIZEN_STATE.OVERDUE) {
                entry.status.setText('Impaye');
                entry.status.setColor('#fdba74');
                entry.marker.setFillStyle(0xf97316, 1);
            } else if (entry.citizen.state === CITIZEN_STATE.CUT_OFF) {
                entry.status.setText('Eau coupee');
                entry.status.setColor('#fca5a5');
                entry.marker.setFillStyle(0xef4444, 1);
            } else {
                entry.status.setText('Remise en eau');
                entry.status.setColor('#93c5fd');
                entry.marker.setFillStyle(0x38bdf8, 1);
            }
        });
    }

    handleInteractionPrompt() {
        const playerPosition = this.player.getPosition();
        const prompt = this.getNearbyInteraction(playerPosition);
        this.interactionText.setText(prompt ? prompt.message : 'Survolez la carte et approchez-vous d un ouvrage ou d un usager.');

        const actionPressed = Phaser.Input.Keyboard.JustDown(this.keys.E) ||
            Phaser.Input.Keyboard.JustDown(this.keys.ENTER) ||
            Phaser.Input.Keyboard.JustDown(this.keys.SPACE);

        if (prompt && actionPressed) {
            prompt.action();
        }
    }

    getNearbyInteraction(playerPosition) {
        for (const entry of this.facilityViews) {
            if (Phaser.Math.Distance.Between(playerPosition.x, playerPosition.y, entry.sprite.x, entry.sprite.y) < 150) {
                if (entry.facility.state === FACILITY_STATE.BROKEN) {
                    return {
                        message: `Action - Reparer ${entry.facility.name} (3 s)`,
                        action: () => this.startFacilityRepair(entry.facility),
                    };
                }
            }
        }

        for (const entry of this.citizenViews) {
            if (Phaser.Math.Distance.Between(playerPosition.x, playerPosition.y, entry.sprite.x, entry.sprite.y) < 115) {
                if (entry.citizen.state === CITIZEN_STATE.DUE || entry.citizen.state === CITIZEN_STATE.OVERDUE || entry.citizen.state === CITIZEN_STATE.CUT_OFF) {
                    return {
                        message: `Action - Encaisser ${entry.citizen.name}`,
                        action: () => this.startPaymentCollection(entry.citizen),
                    };
                }
                if (entry.citizen.state === CITIZEN_STATE.RESTORE_PENDING) {
                    return {
                        message: `Action - Remettre l eau chez ${entry.citizen.name}`,
                        action: () => this.startWaterRestore(entry.citizen),
                    };
                }
            }
        }

        return null;
    }

    startFacilityRepair(facility) {
        if (!this.state.beginRepair(facility)) {
            return;
        }

        this.time.delayedCall(3000, () => {
            if (facility.state === FACILITY_STATE.REPAIRING) {
                this.state.completeRepair(facility);
            }
        });
    }

    startPaymentCollection(citizen) {
        if (citizen.interactionInProgress) {
            return;
        }
        citizen.interactionInProgress = true;
        this.state.pushFeed(`Encaissement en cours chez ${citizen.name}...`);
        this.time.delayedCall(1600, () => {
            this.state.collectPayment(citizen);
            citizen.interactionInProgress = false;
        });
    }

    startWaterRestore(citizen) {
        if (citizen.interactionInProgress) {
            return;
        }
        citizen.interactionInProgress = true;
        this.state.pushFeed(`Remise en eau en cours chez ${citizen.name}...`);
        this.time.delayedCall(1400, () => {
            this.state.restoreWater(citizen);
            citizen.interactionInProgress = false;
        });
    }

    refreshHud() {
        this.eventBus.emit('hud:update', {
            score: this.state.score,
            satisfaction: this.state.satisfaction,
            pendingBreakdowns: this.state.getPendingBreakdowns(),
            pendingPayments: this.state.getPendingPayments(),
            timeLeft: Math.ceil(this.state.timeLeft),
            minVictoryScore: this.gameConfig.minVictoryScore,
            feed: this.state.feed,
            facilities: this.state.facilities,
        });
    }

    checkEndState() {
        if (this.finished) {
            return;
        }

        const endState = this.state.getEndState();
        if (!endState) {
            return;
        }

        this.finished = true;
        this.physics.pause();
        this.player.sprite.setVelocity(0, 0);
        this.eventBus.emit('hud:end', endState);
        this.time.delayedCall(2600, () => {
            this.scene.restart({ gameConfig: this.gameConfig });
        });
    }
}
