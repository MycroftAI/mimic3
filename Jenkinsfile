// Copyright 2022 Mycroft AI Inc.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.
//
// -----------------------------------------------------------------------------
//
// Jenkins pipeline for building Mimic 3 artifacts.
//
// Requires Docker buildx: https://docs.docker.com/buildx/working-with-buildx/
// Assumes the en_UK/apope_low voice is in /home/jenkins/.local/share/mycroft/mimic3/voices

pipeline {
    agent any

    environment {
        DOCKER_BUILDKIT = '1'
        DOCKER_PLATFORM = 'linux/amd64,linux/arm64,linux/arm/v7'
        DEFAULT_VOICE = 'en_UK/apope_low'
        DEFAULT_VOICE_PATH = '/home/jenkins/.local/share/mycroft/mimic3/voices'
    }

    stages {
        // Clone the source code from Github
        stage('Clone') {
            steps {
                git branch: 'master',
                    credentialsId: 'devops-mycroft',
                    url: 'https://github.com/MycroftAI/mimic3.git'

                // Mycroft TTS plugin
                dir('plugin-tts-mimic3') {
                    git branch: 'master',
                        credentialsId: 'devops-mycroft',
                        url: 'https://github.com/MycroftAI/plugin-tts-mimic3'
                }
            }
        }

        // Copy default voice
        stage('Copy voices') {
            steps {
                sh 'mkdir -p voices/${DEFAULT_VOICE}'
                sh 'rsync -r --link-dest="${DEFAULT_VOICE_PATH}/${DEFAULT_VOICE}/" "${DEFAULT_VOICE_PATH}/${DEFAULT_VOICE}/" voices/${DEFAULT_VOICE}/'
            }
        }
        // Build, test, and publish plugin distribution package to PyPI
        stage('Plugin dist') {
            steps {
                sh 'make plugin-dist'
            }
        }

        // Build, test, and publish source distribution packages to PyPI
        stage('Dist') {
            steps {
                sh 'make dist'
            }
        }

        // Build and publish multi-platform Docker image to Dockerhub
        stage('Docker') {
            steps {
                sh 'make docker'
              //sh 'make docker-gpu'
            }
        }


        // Build and publish Debian packages to Github
        stage('Debian') {
            steps {
                sh 'make debian'
            }
        }
    }
}
