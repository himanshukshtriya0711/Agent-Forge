// Get the todo list and new todo input elements
const todoList = document.getElementById('todo-list');
const newTodoInput = document.getElementById('new-todo');
const addTodoButton = document.getElementById('add-todo');

// Initialize an empty array to store the todos
let todos = [];

// Add event listener to the add todo button
addTodoButton.addEventListener('click', addTodo);

// Function to add a new todo
function addTodo() {
    // Get the new todo text
    const newTodoText = newTodoInput.value.trim();
    
    // Check if the new todo text is not empty
    if (newTodoText) {
        // Add the new todo to the array
        todos.push(newTodoText);
        
        // Clear the new todo input
        newTodoInput.value = '';
        
        // Update the todo list
        updateTodoList();
    }
}

// Function to update the todo list
function updateTodoList() {
    // Clear the todo list
    todoList.innerHTML = '';
    
    // Loop through the todos and add them to the list
    todos.forEach((todo, index) => {
        const todoListItem = document.createElement('li');
        todoListItem.textContent = todo;
        todoList.appendChild(todoListItem);
    });
}