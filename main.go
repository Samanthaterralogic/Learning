package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gorilla/mux"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// Student struct represents the schema for the student marks.
type Student struct {
	ID    primitive.ObjectID `json:"id,omitempty" bson:"_id,omitempty"`
	Name  string             `json:"name,omitempty" bson:"name,omitempty"`
	Marks int                `json:"marks,omitempty" bson:"marks,omitempty"`
	Grade string             `json:"grade,omitempty" bson:"grade,omitempty"`
}

var client *mongo.Client

// Connect to MongoDB
func connectDB() {
	clientOptions := options.Client().ApplyURI("mongodb://localhost:27017")

	var err error
	client, err = mongo.Connect(context.Background(), clientOptions)
	if err != nil {
		log.Fatal("Error connecting to MongoDB:", err)
	}

	err = client.Ping(context.Background(), nil)
	if err != nil {
		log.Fatal("Error pinging MongoDB:", err)
	}

	fmt.Println("Connected to MongoDB!")
}

// Create a student record
func createStudent(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Content-Type", "application/json")

	// Check if the MongoDB client is connected
	if client == nil {
		http.Error(response, "MongoDB client is not connected", http.StatusInternalServerError)
		return
	}

	var student Student
	err := json.NewDecoder(request.Body).Decode(&student)
	if err != nil {
		http.Error(response, "Error decoding request body", http.StatusBadRequest)
		return
	}

	collection := client.Database("school").Collection("students")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	result, err := collection.InsertOne(ctx, student)
	if err != nil {
		http.Error(response, "Error inserting student into database", http.StatusInternalServerError)
		return
	}

	// Respond with the inserted ID
	json.NewEncoder(response).Encode(result.InsertedID)
}

// Update a student record by ID
func updateStudent(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("content-type", "application/json")

	params := mux.Vars(request)
	id := params["id"]

	fmt.Println("Updating student with ID:", id)

	// Convert string ID to ObjectId
	objectID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		http.Error(response, "Invalid ObjectID", http.StatusBadRequest)
		return
	}

	var studentUpdate Student
	_ = json.NewDecoder(request.Body).Decode(&studentUpdate)

	// Check if the MongoDB client is connected
	if client == nil {
		http.Error(response, "MongoDB client is not connected", http.StatusInternalServerError)
		return
	}

	collection := client.Database("school").Collection("students")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	filter := bson.M{"_id": objectID}
	update := bson.M{"$set": studentUpdate}

	result, err := collection.UpdateOne(ctx, filter, update)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Println("Update result:", result)

	json.NewEncoder(response).Encode(result)
}

// deletes the students by id
func deleteStudent(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("content-type", "application/json")

	params := mux.Vars(request)
	id := params["id"]

	// Convert the received ID to MongoDB ObjectID
	objID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		fmt.Println("Invalid ID format:", err)
		http.Error(response, "Invalid ID format", http.StatusBadRequest)
		return
	}

	collection := client.Database("school").Collection("students")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	result, err := collection.DeleteOne(ctx, bson.M{"_id": objID})
	if err != nil {
		fmt.Println("Error deleting student record:", err)
		http.Error(response, "Error deleting student record", http.StatusInternalServerError)
		return
	}

	fmt.Printf("Delete result: %+v\n", result)

	json.NewEncoder(response).Encode(result)
}

// Get all students
func getAllStudents(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("content-type", "application/json")

	var students []Student
	collection := client.Database("school").Collection("students")
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	cur, err := collection.Find(ctx, bson.D{})
	if err != nil {
		log.Fatal(err)
	}
	defer cur.Close(ctx)

	for cur.Next(ctx) {
		var student Student
		err := cur.Decode(&student)
		if err != nil {
			log.Fatal(err)
		}
		students = append(students, student)
	}

	if err := cur.Err(); err != nil {
		log.Fatal(err)
	}

	json.NewEncoder(response).Encode(students)
}

func main() {
	connectDB()

	router := mux.NewRouter()
	router.HandleFunc("/students", createStudent).Methods("POST")
	router.HandleFunc("/students", getAllStudents).Methods("GET")
	router.HandleFunc("/students/{id}", updateStudent).Methods("PUT")
	router.HandleFunc("/students/{id}", deleteStudent).Methods("DELETE")

	fmt.Println("Server listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", router))
}
