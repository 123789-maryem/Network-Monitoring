# Network Monitoring System

## Description

Application web de supervision réseau permettant de surveiller l'état des équipements à partir de leur adresse IP.

## Fonctionnalités

- Ajouter un équipement réseau
- Vérifier sa disponibilité avec Ping
- Afficher l'état UP / DOWN
- Afficher le temps de réponse en millisecondes
- Supprimer un équipement
- Sauvegarder les équipements dans une base SQLite
- Afficher des statistiques sur les équipements

## Technologies utilisées

- Python
- Flask
- SQLite
- HTML / CSS
- Git / GitHub

## Architecture

L'application utilise Flask comme backend et SQLite comme base de données.

Utilisateur → Interface Web → Flask → SQLite  
                             ↓  
                           Ping

## Installation

Créer et activer un environnement virtuel :

```bash
python -m venv venv