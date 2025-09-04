// Middleware d'authentification pour les routes API

function requireAuth(req, res, next) {
  // Si la base de données n'est pas initialisée, rediriger vers setup
  if (!global.isDatabaseReady) {
    return res.status(503).json({
      success: false,
      error: 'Base de données non initialisée',
      redirect: '/setup-database'
    });
  }

  if (req.session && req.session.user) {
    return next();
  }

  // Pour les requêtes AJAX/API, retourner une erreur JSON
  if (req.xhr || req.headers.accept?.includes('application/json')) {
    return res.status(401).json({
      success: false,
      error: 'Non autorisé - Session expirée',
      redirect: '/login'
    });
  }

  // Pour les requêtes normales, rediriger vers login
  return res.redirect('/login');
}

function requireApiAuth(req, res, next) {
  // Vérifier l'authentification de session
  if (req.session && req.session.user) {
    return next();
  }

  // Retourner une erreur JSON pour les API
  return res.status(401).json({
    success: false,
    error: 'Non autorisé - Authentification requise',
    code: 'AUTH_REQUIRED'
  });
}

function requireAdmin(req, res, next) {
  if (!req.session || !req.session.user) {
    if (req.xhr || req.headers.accept?.includes('application/json')) {
      return res.status(401).json({
        success: false,
        error: 'Non autorisé - Session expirée'
      });
    }
    return res.redirect('/login');
  }

  // Vérifier si l'utilisateur est admin (role admin ou surnom spécifique)
  const user = req.session.user;
  const isAdmin = user.role === 'admin' || user.surnom === 'admin' || user.surnom === 'herizo';
  
  if (!isAdmin) {
    if (req.xhr || req.headers.accept?.includes('application/json')) {
      return res.status(403).json({
        success: false,
        error: 'Accès refusé - Droits administrateur requis'
      });
    }
    return res.status(403).send('Accès refusé - Droits administrateur requis');
  }

  next();
}

module.exports = {
  requireAuth,
  requireApiAuth,
  requireAdmin
};