// ============================================================
// 文件: state.js | 职责: 前端全局可变状态（所有模块共享同一对象引用）
// ============================================================

export const state = {
    currentMode: 'chat',
    rpgState: { sessionId: null, world: null, playerName: '', storyline: [], sections: null },
    currentUser: null,
    isShared: false,
    rpgAbortController: null,
    _rpgRequestActive: false,
    _gameStarting: false,
    isSwitchingMode: false,
    isSwitchingAgent: false,
    agentState: {},
    currentAgentId: null,
    csrfToken: '',
    isSending: false,
    currentPickedRating: 0,
    skillCheckTimer: null,
    actGameStatusTimeout: null,
    editingAgentId: null,
    editingWorldId: null,
    editingModelId: null,
    spectateTimer: null,
    spectateToken: '',
    spectateMode: 'shared',
    spectateRefreshTimer: null,
    // [AUDIT-Q30] _timers 无 beforeunload 清理，页面关闭时定时器泄漏
    _timers: new Set(),
    _editingSubId: null,
};
