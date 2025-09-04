import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

// Enregistrement des modules Chart.js nécessaires
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

// On peut réutiliser le composant StatCard de SuiviAvances, ou en créer un dédié
const StatCard = ({ title, value, icon, color }) => (
  <div style={{
    background: 'rgba(255, 255, 255, 0.1)',
    padding: '1.5rem',
    borderRadius: '12px',
    textAlign: 'center',
    border: `1px solid ${color}`
  }}>
    <div style={{ fontSize: '2rem' }}>{icon}</div>
    <h3 style={{ fontSize: '2.5rem', margin: '0.5rem 0', color: '#fff' }}>{value}</h3>
    <p style={{ margin: 0, color: 'rgba(255, 255, 255, 0.8)' }}>{title}</p>
  </div>
);

const Dashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        console.log('Fetching dashboard data...');
        const response = await axios.get('/api/dashboard', { withCredentials: true });
        console.log('Dashboard response:', response.data);
        setDashboardData(response.data);
      } catch (err) {
        console.error('Dashboard error:', err);
        console.error('Error response:', err.response);
        if (err.response?.status === 401) {
          setError('Session expirée. Veuillez vous reconnecter.');
        } else if (err.response?.status === 404) {
          setError('API dashboard non trouvée. Vérifiez le serveur backend.');
        } else {
          setError(`Erreur ${err.response?.status || 'réseau'}: ${err.response?.data?.error || err.message}`);
        }
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return <div>🔄 Chargement du dashboard...</div>;
  if (error) return <div style={{ color: 'red' }}>⚠️ {error}</div>;

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { position: 'top', labels: { color: '#fff' } },
      title: { display: true, text: 'Plannings créés par mois', color: '#fff', font: { size: 18 } },
    },
    scales: {
      y: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.2)' } },
      x: { ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.2)' } },
    },
  };

  const chartData = {
    labels: dashboardData.chartData.labels,
    datasets: [
      {
        label: 'Nombre de Plannings',
        data: dashboardData.chartData.data,
        backgroundColor: 'rgba(54, 162, 235, 0.6)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1,
      },
    ],
  };

  return (
    <div style={{ padding: '2rem', color: '#fff' }}>
      <h1 style={{ textAlign: 'center', marginBottom: '2rem' }}>Dashboard Principal</h1>

      {/* Cartes de statistiques */}
      <section style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.5rem',
        marginBottom: '3rem'
      }}>
        <StatCard title="Employés" value={dashboardData.stats.employes} icon="👥" color="#17a2b8" />
        <StatCard title="Ouvrages" value={dashboardData.stats.ouvrages} icon="🏗️" color="#ffc107" />
        <StatCard title="Plannings" value={dashboardData.stats.plannings} icon="🗓️" color="#28a745" />
      </section>

      {/* Section du graphique */}
      <section style={{ background: 'rgba(255, 255, 255, 0.05)', padding: '2rem', borderRadius: '12px' }}>
        <Bar options={chartOptions} data={chartData} />
      </section>
    </div>
  );
};

export default Dashboard;