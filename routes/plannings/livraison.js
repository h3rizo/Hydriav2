const express = require('express');
const router = express.Router();
router.get('/plannings/livraison', (req, res) => {
  if (!req.session.user) {
    return res.redirect('/login');
  }
  res.render('plannings/livraison', { user: req.session.user });
});
module.exports = router;