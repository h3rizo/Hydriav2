const FACILITY_STATE = {
    HEALTHY: 'healthy',
    BROKEN: 'broken',
    REPAIRING: 'repairing',
};

const CITIZEN_STATE = {
    DUE: 'due',
    OVERDUE: 'overdue',
    CUT_OFF: 'cut_off',
    RESTORE_PENDING: 'restore_pending',
};

export class GameState {
    constructor(config) {
        this.config = config;
        this.score = 0;
        this.satisfaction = 100;
        this.timeLeft = config.durationSeconds;
        this.missedBreakdowns = 0;
        this.feed = ['Supervisez plusieurs ouvrages et priorisez les urgences.'];
        this.facilities = this.createFacilities();
        this.citizens = this.createCitizens();
    }

    createFacilities() {
        return [
            this.createFacility('ouvrage_nord', 'Ouvrage Nord', 460, 300, 9),
            this.createFacility('ouvrage_centre', 'Ouvrage Centre', 1080, 620, 14),
            this.createFacility('ouvrage_sud', 'Ouvrage Sud', 1780, 980, 20),
            this.createFacility('ouvrage_est', 'Ouvrage Est', 2140, 380, 26),
        ];
    }

    createFacility(id, name, x, y, nextFailureAt) {
        return {
            id,
            name,
            x,
            y,
            state: FACILITY_STATE.HEALTHY,
            failureDeadline: null,
            nextFailureAt,
            repairInProgress: false,
        };
    }

    createCitizens() {
        return [
            this.createCitizen('Aina', 1, 'ouvrage_nord', 8),
            this.createCitizen('Tiana', 2, 'ouvrage_nord', 15),
            this.createCitizen('Soa', 3, 'ouvrage_centre', 10),
            this.createCitizen('Mamy', 4, 'ouvrage_centre', 18),
            this.createCitizen('Hery', 5, 'ouvrage_sud', 12),
            this.createCitizen('Lova', 6, 'ouvrage_est', 16),
        ];
    }

    createCitizen(name, id, facilityId, firstDueAt) {
        return {
            id,
            name,
            facilityId,
            state: CITIZEN_STATE.DUE,
            dueAt: firstDueAt,
            overdueAt: firstDueAt + 9,
            cutOffAt: firstDueAt + 18,
            interactionInProgress: false,
        };
    }

    tick(deltaSeconds) {
        this.timeLeft = Math.max(0, this.timeLeft - deltaSeconds);
        const elapsed = this.config.durationSeconds - this.timeLeft;

        this.facilities.forEach((facility) => {
            if (facility.state === FACILITY_STATE.HEALTHY && elapsed >= facility.nextFailureAt) {
                facility.state = FACILITY_STATE.BROKEN;
                facility.failureDeadline = elapsed + 14;
                facility.nextFailureAt = elapsed + Phaser.Math.Between(18, 28);
                this.adjustSatisfaction(-3);
                this.pushFeed(`Panne detectee sur ${facility.name}.`);
            }

            if (facility.state === FACILITY_STATE.BROKEN && elapsed > facility.failureDeadline) {
                facility.state = FACILITY_STATE.HEALTHY;
                facility.failureDeadline = null;
                facility.repairInProgress = false;
                this.missedBreakdowns += 1;
                this.score -= 18;
                this.adjustSatisfaction(-12);
                this.pushFeed(`Panne non traitee a temps sur ${facility.name}.`);
            }
        });

        this.citizens.forEach((citizen) => {
            if (citizen.state === CITIZEN_STATE.DUE && elapsed > citizen.overdueAt) {
                citizen.state = CITIZEN_STATE.OVERDUE;
                this.adjustSatisfaction(-5);
                this.pushFeed(`${citizen.name} devient impaye.`);
            }

            if (citizen.state === CITIZEN_STATE.OVERDUE && elapsed > citizen.cutOffAt) {
                citizen.state = CITIZEN_STATE.CUT_OFF;
                this.adjustSatisfaction(-9);
                this.pushFeed(`Eau coupee chez ${citizen.name}.`);
            }
        });
    }

    beginRepair(facility) {
        if (facility.state === FACILITY_STATE.BROKEN && !facility.repairInProgress) {
            facility.repairInProgress = true;
            facility.state = FACILITY_STATE.REPAIRING;
            this.pushFeed(`Equipe envoyee sur ${facility.name}.`);
            return true;
        }
        return false;
    }

    completeRepair(facility) {
        facility.state = FACILITY_STATE.HEALTHY;
        facility.failureDeadline = null;
        facility.repairInProgress = false;
        this.score += 22;
        this.adjustSatisfaction(7);
        this.pushFeed(`${facility.name} repare dans les delais.`);
    }

    collectPayment(citizen) {
        if (citizen.state === CITIZEN_STATE.DUE) {
            this.score += 14;
            this.adjustSatisfaction(3);
            this.pushFeed(`Paiement collecte a temps chez ${citizen.name}.`);
            this.resetCitizenCycle(citizen);
            return;
        }

        if (citizen.state === CITIZEN_STATE.OVERDUE) {
            this.score += 6;
            this.adjustSatisfaction(2);
            this.pushFeed(`Impaye regularise chez ${citizen.name}.`);
            this.resetCitizenCycle(citizen);
            return;
        }

        if (citizen.state === CITIZEN_STATE.CUT_OFF) {
            citizen.state = CITIZEN_STATE.RESTORE_PENDING;
            this.pushFeed(`Paiement recu chez ${citizen.name}, remise en eau requise.`);
        }
    }

    restoreWater(citizen) {
        this.score += 10;
        this.adjustSatisfaction(5);
        this.pushFeed(`Remise en eau effectuee chez ${citizen.name}.`);
        this.resetCitizenCycle(citizen, true);
    }

    resetCitizenCycle(citizen, restored = false) {
        const elapsed = this.config.durationSeconds - this.timeLeft;
        const baseOffset = restored ? 16 : 20;
        citizen.state = CITIZEN_STATE.DUE;
        citizen.dueAt = elapsed + baseOffset;
        citizen.overdueAt = citizen.dueAt + 9;
        citizen.cutOffAt = citizen.overdueAt + 9;
        citizen.interactionInProgress = false;
    }

    adjustSatisfaction(amount) {
        this.satisfaction = Phaser.Math.Clamp(this.satisfaction + amount, 0, 100);
    }

    getPendingBreakdowns() {
        return this.missedBreakdowns + this.facilities.filter((facility) => facility.state !== FACILITY_STATE.HEALTHY).length;
    }

    getPendingPayments() {
        return this.citizens.filter((citizen) => citizen.state !== CITIZEN_STATE.DUE).length;
    }

    getFailureReason() {
        if (this.satisfaction <= this.config.failureSatisfactionThreshold) {
            return 'Satisfaction trop basse';
        }
        if (this.getPendingBreakdowns() > this.config.failureMaxPendingBreakdowns) {
            return 'Trop de pannes non traitees';
        }
        return null;
    }

    getEndState() {
        const failureReason = this.getFailureReason();
        if (failureReason) {
            return { status: 'failure', reason: failureReason };
        }
        if (this.timeLeft <= 0) {
            if (this.score >= this.config.minVictoryScore) {
                return { status: 'victory', reason: 'Vous avez maintenu le reseau multi-sites.' };
            }
            return { status: 'failure', reason: 'Score insuffisant a la fin de la mission.' };
        }
        return null;
    }

    getFacilityById(facilityId) {
        return this.facilities.find((facility) => facility.id === facilityId) || null;
    }

    getCitizensForFacility(facilityId) {
        return this.citizens.filter((citizen) => citizen.facilityId === facilityId);
    }

    pushFeed(message) {
        this.feed.unshift(message);
        this.feed = this.feed.slice(0, 6);
    }
}

export { CITIZEN_STATE, FACILITY_STATE };
