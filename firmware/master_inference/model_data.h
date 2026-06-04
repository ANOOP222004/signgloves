// model_data.h — extern declarations for TFLite model.
// The actual array lives in model_data.cpp
// (split to avoid cc1plus.exe out-of-memory on Windows).
#ifndef MODEL_DATA_H
#define MODEL_DATA_H

extern const unsigned char g_model[];
extern const unsigned int  g_model_len;

#endif // MODEL_DATA_H
