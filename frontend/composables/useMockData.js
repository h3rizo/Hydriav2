// Composable pour les données simulées (mode offline)
export const useMockData = () => {
  // Utilisateur simulé
  const mockUser = {
    id: 1,
    username: 'admin',
    first_name: 'Administrateur',
    last_name: 'Hydria',
    email: 'admin@hydria.mg',
    is_staff: true,
    is_authenticated: true
  }

  // Données de tableaux de bord simulées
  const mockDashboardData = {
    overview: {
      total_payments: 2450000,
      total_expenses: 1200000,
      active_bases: 8,
      pending_invoices: 15
    },
    payments_flat: {
      monthly_total: 850000,
      bases_count: 5,
      average_per_base: 170000
    },
    payments_volume: {
      monthly_total: 1600000,
      total_volume: 45000,
      average_price: 35.6
    },
    expenses: {
      monthly_total: 1200000,
      categories: [
        { name: 'Transport', amount: 450000 },
        { name: 'Maintenance', amount: 320000 },
        { name: 'Personnel', amount: 280000 },
        { name: 'Fournitures', amount: 150000 }
      ]
    }
  }

  // Plannings simulés
  const mockPlannings = [
    {
      id: 1,
      date: '2025-09-18',
      base: 'Antananarivo Centre',
      employee: 'Rakoto Jean',
      type: 'Livraison',
      status: 'En cours',
      amount: 150000
    },
    {
      id: 2,
      date: '2025-09-19',
      base: 'Antsirabe',
      employee: 'Rasoa Marie',
      type: 'Maintenance',
      status: 'Planifié',
      amount: 80000
    },
    {
      id: 3,
      date: '2025-09-20',
      base: 'Fianarantsoa',
      employee: 'Andry Paul',
      type: 'Inspection',
      status: 'Planifié',
      amount: 45000
    }
  ]

  // Factures simulées
  const mockInvoices = [
    {
      id: 'F001',
      client: 'Base Antananarivo',
      amount: 180000,
      due_date: '2025-09-25',
      status: 'Impayée',
      type: 'Forfaitaire'
    },
    {
      id: 'F002',
      client: 'Base Antsirabe',
      amount: 95000,
      due_date: '2025-09-30',
      status: 'Payée',
      type: 'Volumétrique'
    },
    {
      id: 'F003',
      client: 'Base Fianarantsoa',
      amount: 120000,
      due_date: '2025-10-05',
      status: 'Impayée',
      type: 'Forfaitaire'
    }
  ]

  // Stocks simulés
  const mockInventory = [
    {
      id: 1,
      item: 'Tuyaux PVC 32mm',
      current_stock: 45,
      min_stock: 20,
      unit_price: 8500,
      category: 'Plomberie'
    },
    {
      id: 2,
      item: 'Pompes électriques 1HP',
      current_stock: 8,
      min_stock: 5,
      unit_price: 450000,
      category: 'Équipement'
    },
    {
      id: 3,
      item: 'Compteurs d\'eau',
      current_stock: 12,
      min_stock: 10,
      unit_price: 85000,
      category: 'Comptage'
    }
  ]

  // Simulation d'API calls
  const mockApiCall = (delay = 1000) => {
    return new Promise((resolve) => {
      setTimeout(resolve, delay)
    })
  }

  // Fonctions simulées d'API
  const fetchDashboard = async () => {
    await mockApiCall(800)
    return mockDashboardData
  }

  const fetchPlannings = async () => {
    await mockApiCall(600)
    return mockPlannings
  }

  const fetchInvoices = async () => {
    await mockApiCall(700)
    return mockInvoices
  }

  const fetchInventory = async () => {
    await mockApiCall(500)
    return mockInventory
  }

  const fetchUser = async () => {
    await mockApiCall(300)
    return mockUser
  }

  // Simulation de requêtes de chat IA
  const mockAiResponses = [
    "D'après les données actuelles, vous avez 15 factures impayées pour un montant total de 300 000 Ar.",
    "Cette semaine, 3 plannings sont programmés : 1 livraison et 2 inspections.",
    "Le stock de tuyaux PVC 32mm est suffisant (45 unités) mais surveillez les pompes électriques (8 unités restantes).",
    "Les paiements forfaitaires représentent 35% du chiffre d'affaires ce mois-ci.",
    "La base d'Antananarivo a la meilleure performance avec 180 000 Ar de chiffre d'affaires."
  ]

  const mockChatResponse = async (message) => {
    await mockApiCall(1500)
    const randomResponse = mockAiResponses[Math.floor(Math.random() * mockAiResponses.length)]
    return {
      response: randomResponse,
      timestamp: new Date().toISOString()
    }
  }

  return {
    mockUser,
    mockDashboardData,
    mockPlannings,
    mockInvoices,
    mockInventory,
    fetchDashboard,
    fetchPlannings,
    fetchInvoices,
    fetchInventory,
    fetchUser,
    mockChatResponse,
    mockApiCall
  }
}