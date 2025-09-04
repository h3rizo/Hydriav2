import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  DndContext,
  DragOverlay,
  closestCorners,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import {
  useSortable,
} from '@dnd-kit/sortable';
import { useDroppable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';

// Composant de carte draggable
const DraggableCard = ({ planning, onEdit, columnColor }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: planning.id.toString() });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('fr-FR');
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
    >
      <div style={{
        background: 'rgba(255, 255, 255, 0.08)',
        borderRadius: '8px',
        padding: '1rem',
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
        borderLeft: `4px solid ${columnColor}`,
        cursor: isDragging ? 'grabbing' : 'grab',
        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        marginBottom: '1rem'
      }}
      onMouseEnter={(e) => {
        if (!isDragging) {
          e.target.style.transform = 'translateY(-2px)';
          e.target.style.boxShadow = '0 4px 12px rgba(0,0,0,0.4)';
        }
      }}
      onMouseLeave={(e) => {
        if (!isDragging) {
          e.target.style.transform = 'translateY(0)';
          e.target.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)';
        }
      }}>
        <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1rem' }}>
          {planning.employe?.nom ? `${planning.employe.prenom || ''} ${planning.employe.nom}`.trim() : 'Employé N/A'}
        </h4>
        
        <p style={{ margin: '0.25rem 0', fontSize: '0.9rem', color: 'rgba(255, 255, 255, 0.7)' }}>
          📍 <strong>Ouvrage:</strong> {planning.ouvrage?.nom || 'N/A'}
        </p>
        
        <p style={{ margin: '0.25rem 0', fontSize: '0.9rem', color: 'rgba(255, 255, 255, 0.7)' }}>
          🏢 <strong>Organisation:</strong> {planning.organisation?.nom || 'N/A'}
        </p>

        {planning.Bilan && (
          <p style={{ 
            margin: '0.5rem 0', 
            fontSize: '0.8rem', 
            color: 'rgba(255, 255, 255, 0.6)',
            fontStyle: 'italic',
            maxHeight: '40px',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            💬 {planning.Bilan.replace(/<[^>]*>/g, '').substring(0, 80)}...
          </p>
        )}

        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: '1rem',
          fontSize: '0.8rem',
          color: 'rgba(255, 255, 255, 0.6)'
        }}>
          <span style={{ fontWeight: 'bold' }}>
            📅 {formatDate(planning.DatePlanning)}
          </span>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button 
              onClick={(e) => {
                e.stopPropagation();
                onEdit(planning, 'bilan');
              }}
              style={{
                background: 'rgba(255, 255, 255, 0.1)',
                color: '#fff',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '4px',
                padding: '0.25rem 0.5rem',
                fontSize: '0.75rem',
                cursor: 'pointer',
                transition: 'background 0.2s ease'
              }}
              onMouseEnter={(e) => e.target.style.background = 'rgba(255, 255, 255, 0.2)'}
              onMouseLeave={(e) => e.target.style.background = 'rgba(255, 255, 255, 0.1)'}
            >
              ✏️ Modifier
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// Composant de colonne droppable
const DroppableColumn = ({ column, plannings, onEdit, children }) => {
  const { setNodeRef, isOver } = useDroppable({
    id: column.key,
  });

  return (
    <div
      ref={setNodeRef}
      style={{
        flex: 1,
        minWidth: '320px',
        maxWidth: '350px',
        background: isOver ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.05)',
        borderRadius: '8px',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
        transition: 'background-color 0.2s ease',
        border: isOver ? `2px dashed ${column.color}` : '1px solid rgba(255, 255, 255, 0.1)'
      }}
    >
      {/* Column Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0 0.5rem 1rem 0.5rem',
        borderBottom: `3px solid ${column.color}`,
        marginBottom: '1rem'
      }}>
        <h3 style={{ margin: 0, fontSize: '1.1rem', color: column.color }}>
          {column.label}
        </h3>
        <span style={{
          background: '#e0e0e0',
          color: '#333',
          borderRadius: '10px',
          padding: '2px 8px',
          fontSize: '0.9rem',
          fontWeight: 'bold'
        }}>
          {plannings?.length || 0}
        </span>
      </div>

      {/* Cards */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        flexGrow: 1,
        overflowY: 'auto',
        paddingRight: '5px',
        minHeight: '200px'
      }}>
        {children}
      </div>
    </div>
  );
};

const PlanningKanban = () => {
  const [plannings, setPlannings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedPlanning, setSelectedPlanning] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalData, setModalData] = useState({ bilan: '', suiteADonner: '' });
  const [activeId, setActiveId] = useState(null);

  // Configuration des capteurs pour le drag and drop
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Colonnes du Kanban avec leurs couleurs et labels
  const kanbanColumns = [
    { key: 'attente', label: 'En Attente', color: '#6c757d', bgColor: 'rgba(108, 117, 125, 0.1)' },
    { key: 'en_cours', label: 'En Cours', color: '#ffc107', bgColor: 'rgba(255, 193, 7, 0.1)' },
    { key: 'termine', label: 'Terminé', color: '#28a745', bgColor: 'rgba(40, 167, 69, 0.1)' },
    { key: 'livre', label: 'Livré', color: '#007bff', bgColor: 'rgba(0, 123, 255, 0.1)' }
  ];

  useEffect(() => {
    fetchPlannings();
  }, []);

  const fetchPlannings = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/api/react/kanban', { withCredentials: true });
      setPlannings(response.data.plannings || []);
    } catch (err) {
      console.error('Erreur lors du chargement:', err);
      setError('Impossible de charger les plannings');
    } finally {
      setLoading(false);
    }
  };

  const getStatusFromPlanning = (planning) => {
    if (planning.EstLivre) return 'livre';
    if (planning.EstTermine) return 'termine';
    if (planning.EstEnCours) return 'en_cours';
    return 'attente';
  };

  // Fonctions de gestion du drag and drop
  const handleDragStart = (event) => {
    setActiveId(event.active.id);
  };

  const handleDragOver = (event) => {
    const { active, over } = event;
    if (!over) return;

    const activeId = active.id;
    const overId = over.id;

    // Vérifier si on drag vers une colonne différente
    const activePlanning = plannings.find(p => p.id.toString() === activeId);
    if (!activePlanning) return;

    const activeStatus = getStatusFromPlanning(activePlanning);
    
    // Si on drag vers une colonne (pas vers une carte)
    if (['attente', 'en_cours', 'termine', 'livre'].includes(overId)) {
      const newStatus = overId;
      if (activeStatus !== newStatus) {
        updatePlanningStatus(activePlanning, newStatus);
      }
    }
  };

  const handleDragEnd = (event) => {
    setActiveId(null);
  };

  const updatePlanningStatus = (planning, newStatus) => {
    const updatedPlanning = {
      ...planning,
      EstEnCours: newStatus === 'en_cours',
      EstTermine: newStatus === 'termine',
      EstLivre: newStatus === 'livre'
    };

    setPlannings(prev => prev.map(p => 
      p.id === planning.id ? updatedPlanning : p
    ));

    // TODO: Envoyer la mise à jour au serveur
    console.log(`Planning ${planning.id} moved to ${newStatus}`);
  };

  const groupPlanningsByStatus = () => {
    const grouped = {};
    kanbanColumns.forEach(col => {
      grouped[col.key] = [];
    });

    plannings.forEach(planning => {
      const status = getStatusFromPlanning(planning);
      if (grouped[status]) {
        grouped[status].push(planning);
      }
    });

    return grouped;
  };

  const openModal = (planning, focus = 'bilan') => {
    setSelectedPlanning(planning);
    setModalData({
      bilan: planning.Bilan || '',
      suiteADonner: planning.SuiteADonner || ''
    });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedPlanning(null);
    setModalData({ bilan: '', suiteADonner: '' });
  };

  const saveDetails = async () => {
    if (!selectedPlanning) return;

    try {
      const response = await axios.put(`/plannings/${selectedPlanning.id}/details`, {
        Bilan: modalData.bilan,
        SuiteADonner: modalData.suiteADonner
      }, {
        headers: { 'Content-Type': 'application/json' },
        withCredentials: true
      });

      if (response.status === 200) {
        // Mettre à jour le planning dans la liste
        setPlannings(prev => prev.map(p => 
          p.id === selectedPlanning.id 
            ? { ...p, Bilan: modalData.bilan, SuiteADonner: modalData.suiteADonner }
            : p
        ));
        closeModal();
      }
    } catch (err) {
      console.error('Erreur lors de la sauvegarde:', err);
      alert('Erreur lors de la sauvegarde');
    }
  };

  const groupedPlannings = groupPlanningsByStatus();

  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '400px',
        color: '#fff'
      }}>
        🔄 Chargement du Kanban...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ 
        color: '#dc3545', 
        textAlign: 'center', 
        padding: '2rem',
        background: 'rgba(220, 53, 69, 0.1)',
        borderRadius: '8px',
        border: '1px solid #dc3545'
      }}>
        ⚠️ {error}
      </div>
    );
  }

  return (
    <div style={{ 
      padding: '1.5rem', 
      background: 'linear-gradient(135deg, #0F0C29 0%, #1A1441 25%, #24174C 75%, #2D1F57 100%)',
      minHeight: '100vh',
      color: '#ffffff'
    }}>
      <header style={{ marginBottom: '2rem', textAlign: 'center' }}>
        <h1 style={{ 
          fontSize: '2.5rem', 
          fontWeight: '300', 
          margin: '0 0 0.5rem 0',
          textShadow: '0 2px 4px rgba(0,0,0,0.3)'
        }}>
          📋 Kanban des Plannings
        </h1>
        <p style={{ 
          color: 'rgba(255, 255, 255, 0.8)', 
          fontSize: '1.1rem', 
          margin: 0 
        }}>
          Gestion visuelle des tâches de planification
        </p>
      </header>

      {/* Kanban Board avec Drag and Drop */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
      >
        <div style={{
          display: 'flex',
          gap: '1.5rem',
          overflowX: 'auto',
          paddingBottom: '1rem',
          minHeight: '70vh'
        }}>
          {kanbanColumns.map(column => (
            <DroppableColumn 
              key={column.key} 
              column={column}
              plannings={groupedPlannings[column.key]}
              onEdit={openModal}
            >
              <SortableContext 
                items={groupedPlannings[column.key]?.map(p => p.id.toString()) || []}
                strategy={verticalListSortingStrategy}
              >
                {groupedPlannings[column.key]?.map(planning => (
                  <DraggableCard
                    key={planning.id}
                    planning={planning}
                    onEdit={openModal}
                    columnColor={column.color}
                  />
                ))}
              </SortableContext>
            </DroppableColumn>
          ))}
        </div>

        <DragOverlay>
          {activeId ? (
            <div style={{
              background: 'rgba(255, 255, 255, 0.15)',
              borderRadius: '8px',
              padding: '1rem',
              boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
              borderLeft: '4px solid #007bff',
              transform: 'rotate(5deg)',
              cursor: 'grabbing'
            }}>
              <h4 style={{ margin: 0, fontSize: '1rem', color: '#fff' }}>
                Déplacement en cours...
              </h4>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {/* Modal */}
      {isModalOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: 'rgba(0, 0, 0, 0.7)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #1A1441 0%, #24174C 100%)',
            borderRadius: '12px',
            padding: '2rem',
            maxWidth: '600px',
            width: '90%',
            maxHeight: '80vh',
            overflowY: 'auto',
            color: '#fff',
            border: '1px solid rgba(255, 255, 255, 0.1)'
          }}>
            <h3 style={{ margin: '0 0 1rem 0', color: '#fff' }}>
              Modifier les détails - {selectedPlanning?.employe?.nom}
            </h3>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#fff' }}>
                Bilan:
              </label>
              <textarea
                value={modalData.bilan}
                onChange={(e) => setModalData({...modalData, bilan: e.target.value})}
                style={{
                  width: '100%',
                  minHeight: '120px',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  resize: 'vertical'
                }}
                placeholder="Saisissez le bilan..."
              />
            </div>

            <div style={{ marginBottom: '2rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#fff' }}>
                Suite à donner:
              </label>
              <textarea
                value={modalData.suiteADonner}
                onChange={(e) => setModalData({...modalData, suiteADonner: e.target.value})}
                style={{
                  width: '100%',
                  minHeight: '120px',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  resize: 'vertical'
                }}
                placeholder="Saisissez la suite à donner..."
              />
            </div>

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
              <button
                onClick={closeModal}
                style={{
                  padding: '0.75rem 1.5rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  background: 'transparent',
                  color: '#fff',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  transition: 'background 0.2s ease'
                }}
                onMouseEnter={(e) => e.target.style.background = 'rgba(255, 255, 255, 0.1)'}
                onMouseLeave={(e) => e.target.style.background = 'transparent'}
              >
                Annuler
              </button>
              <button
                onClick={saveDetails}
                style={{
                  padding: '0.75rem 1.5rem',
                  border: 'none',
                  background: '#28a745',
                  color: '#fff',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  transition: 'background 0.2s ease'
                }}
                onMouseEnter={(e) => e.target.style.background = '#218838'}
                onMouseLeave={(e) => e.target.style.background = '#28a745'}
              >
                Enregistrer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PlanningKanban;