export function getGameConfig(rootElement) {
    return {
        width: 1280,
        height: 720,
        worldWidth: 2400,
        worldHeight: 1400,
        durationSeconds: Number(rootElement.dataset.durationSeconds || 120),
        minVictoryScore: Number(rootElement.dataset.minVictoryScore || 80),
        failureSatisfactionThreshold: Number(rootElement.dataset.failureSatisfactionThreshold || 15),
        failureMaxPendingBreakdowns: Number(rootElement.dataset.failureMaxPendingBreakdowns || 3),
    };
}
