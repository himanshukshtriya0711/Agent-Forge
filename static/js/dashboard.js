/* =============================================================================
   AgentForge - Dashboard JavaScript
   Project management functionality
   ============================================================================= */

document.addEventListener('DOMContentLoaded', () => {
    const { API, UI } = window.AgentForge;

    // Elements
    const newProjectBtn = document.getElementById('new-project-btn');
    const emptyNewProjectBtn = document.getElementById('empty-new-project-btn');
    const newProjectModal = document.getElementById('new-project-modal');
    const newProjectForm = document.getElementById('new-project-form');
    const modalClose = document.getElementById('modal-close');
    const modalCancel = document.getElementById('modal-cancel');
    const deleteModal = document.getElementById('delete-modal');
    const deleteCancel = document.getElementById('delete-cancel');
    const deleteConfirm = document.getElementById('delete-confirm');

    let projectToDelete = null;

    // Open new project modal
    function openNewProjectModal() {
        UI.showModal('new-project-modal');
        document.getElementById('project-name').focus();
    }

    // Close new project modal
    function closeNewProjectModal() {
        UI.hideModal('new-project-modal');
        newProjectForm.reset();
    }

    // Create new project
    async function createProject(e) {
        e.preventDefault();
        
        const name = document.getElementById('project-name').value.trim();
        const description = document.getElementById('project-description').value.trim();

        if (!name) {
            UI.toast('Project name is required', 'error');
            return;
        }

        try {
            const submitBtn = newProjectForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Creating...';

            const result = await API.post('/api/projects/create/', { name, description });

            if (result.success) {
                UI.toast('Project created successfully', 'success');
                // Redirect to editor
                window.location.href = `/editor/${result.project.id}/`;
            }
        } catch (error) {
            UI.toast(error.message || 'Failed to create project', 'error');
        } finally {
            const submitBtn = newProjectForm.querySelector('button[type="submit"]');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Create Project';
        }
    }

    // Delete project
    function openDeleteModal(projectId) {
        projectToDelete = projectId;
        UI.showModal('delete-modal');
    }

    function closeDeleteModal() {
        UI.hideModal('delete-modal');
        projectToDelete = null;
    }

    async function confirmDelete() {
        if (!projectToDelete) return;

        try {
            const result = await API.delete(`/api/projects/${projectToDelete}/delete/`);

            if (result.success) {
                UI.toast('Project deleted', 'success');
                // Remove card from DOM
                const card = document.querySelector(`[data-project-id="${projectToDelete}"]`);
                if (card) {
                    card.remove();
                }
                // Check if grid is empty
                const grid = document.getElementById('projects-grid');
                if (!grid.querySelector('.project-card')) {
                    grid.innerHTML = `
                        <div class="empty-state">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                            </svg>
                            <h3>No Projects Yet</h3>
                            <p>Create your first project to get started with AgentForge</p>
                            <button id="empty-new-project-btn" class="btn btn-primary">
                                Create Project
                            </button>
                        </div>
                    `;
                    // Re-attach event listener
                    document.getElementById('empty-new-project-btn')?.addEventListener('click', openNewProjectModal);
                }
            }
        } catch (error) {
            UI.toast(error.message || 'Failed to delete project', 'error');
        } finally {
            closeDeleteModal();
        }
    }

    // Event Listeners
    newProjectBtn?.addEventListener('click', openNewProjectModal);
    emptyNewProjectBtn?.addEventListener('click', openNewProjectModal);
    modalClose?.addEventListener('click', closeNewProjectModal);
    modalCancel?.addEventListener('click', closeNewProjectModal);
    newProjectForm?.addEventListener('submit', createProject);

    deleteCancel?.addEventListener('click', closeDeleteModal);
    deleteConfirm?.addEventListener('click', confirmDelete);

    // Delete buttons on project cards
    document.querySelectorAll('.delete-project-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const projectId = btn.dataset.projectId;
            openDeleteModal(projectId);
        });
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + N: New project
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            openNewProjectModal();
        }
    });
});
