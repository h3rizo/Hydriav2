export class Player {
    constructor(scene, x, y) {
        this.scene = scene;
        this.sprite = scene.physics.add.sprite(x, y, 'player');
        this.sprite.setCollideWorldBounds(true);
        this.sprite.body.setSize(34, 34);
        this.speed = 250;
    }

    update(cursors, keys) {
        const leftPressed = cursors.left.isDown || keys.A.isDown;
        const rightPressed = cursors.right.isDown || keys.D.isDown;
        const upPressed = cursors.up.isDown || keys.W.isDown;
        const downPressed = cursors.down.isDown || keys.S.isDown;

        let velocityX = 0;
        let velocityY = 0;

        if (leftPressed) {
            velocityX -= 1;
            this.sprite.setFlipX(true);
        }
        if (rightPressed) {
            velocityX += 1;
            this.sprite.setFlipX(false);
        }
        if (upPressed) {
            velocityY -= 1;
        }
        if (downPressed) {
            velocityY += 1;
        }

        const vector = new Phaser.Math.Vector2(velocityX, velocityY);
        if (vector.lengthSq() > 0) {
            vector.normalize().scale(this.speed);
        }

        this.sprite.setVelocity(vector.x, vector.y);
    }

    getPosition() {
        return this.sprite.getCenter();
    }
}
