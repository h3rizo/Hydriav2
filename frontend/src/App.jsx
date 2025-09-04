import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import SimpleDashboard from './components/SimpleDashboard.jsx';
import SuiviAvances from './components/SuiviAvance.jsx';
import PlanningKanban from './components/PlanningKanban.jsx';
import PlanningSaisie from './components/PlanningSaisie.jsx';

function App() {
  // Sample user info - this would normally come from authentication context
  const userInfo = {
    organisation: 'SOAKOJA',
    employeName: 'Admin User',
    poste: 'Administrateur',
    niveauMenu: 'Complet'
  };

  return (
    <Layout userInfo={userInfo}>
      <Routes>
        <Route path="/" element={<SimpleDashboard />} />
        <Route path="/suivi-avances" element={<SuiviAvances />} />
        <Route path="/plannings/kanban" element={<PlanningKanban />} />
        <Route path="/plannings/nouveau" element={<PlanningSaisie />} />
        
        {/* Planning routes */}
        <Route path="/plannings/livraisons" element={<div className="animate-fadeIn">🚚 Page Livraisons - En construction</div>} />
        <Route path="/plannings/avances" element={<div className="animate-fadeIn">💰 Page Avances - En construction</div>} />
        <Route path="/plannings/retour" element={<div className="animate-fadeIn">↩️ Page Retour - En construction</div>} />
        <Route path="/plannings/livraison-retour" element={<div className="animate-fadeIn">🔄 Page Livraison Retour - En construction</div>} />
        <Route path="/plannings/retour-avance" element={<div className="animate-fadeIn">💸 Page Retour Avance - En construction</div>} />
        <Route path="/plannings/retour-indemnites" element={<div className="animate-fadeIn">💼 Page Retour Indemnités - En construction</div>} />
        <Route path="/plannings/retour-frais" element={<div className="animate-fadeIn">🚗 Page Retour Frais - En construction</div>} />
        
        {/* Report routes */}
        <Route path="/rapports/saisie" element={<div className="animate-fadeIn">📝 Page Saisie Rapport - En construction</div>} />
        <Route path="/plannings/calendrier" element={<div className="animate-fadeIn">🗓️ Page Vue Calendrier - En construction</div>} />
        <Route path="/rapports/vue" element={<div className="animate-fadeIn">📈 Page Vue Rapport - En construction</div>} />
        
        {/* Other routes placeholders */}
        <Route path="/paiement/*" element={<div className="animate-fadeIn">💳 Section Paiement - En construction</div>} />
        <Route path="/demandes/*" element={<div className="animate-fadeIn">📄 Section Demandes BP - En construction</div>} />
        <Route path="/releves/*" element={<div className="animate-fadeIn">📏 Section Relevés - En construction</div>} />
        <Route path="/cartes/*" element={<div className="animate-fadeIn">🎫 Section Cartes Sociales - En construction</div>} />
        <Route path="/stocks/*" element={<div className="animate-fadeIn">📦 Section Achats et Stocks - En construction</div>} />
        <Route path="/admin/*" element={<div className="animate-fadeIn">⚙️ Section Administration - En construction</div>} />
        <Route path="/diamex/*" element={<div className="animate-fadeIn">🔄 Section DiameX - En construction</div>} />
      </Routes>
    </Layout>
  );
}

export default App;
